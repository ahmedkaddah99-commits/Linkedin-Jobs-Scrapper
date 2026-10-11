# Runr Analytics Specification

Generated from a codebase review on 2026-05-17.

## Coverage
This review covered the current analytical surface across:

- Backend domain and schemas: `backend/domain/models.py`, `backend/domain/phase0_contracts.py`, `backend/domain/ats_export_gate.py`
- Persistence: `backend/repositories/sqlite_backed.py`, `backend/repositories/file_backed.py`, `backend/repositories/mysql_career_discovery.py`
- Application and API: `backend/application/services.py`, `backend/api/server.py`
- Workflow runtime: `backend/orchestration/engine.py`, `backend/orchestration/workspace_builder.py`, `backend/adapters/stage_adapters.py`
- Connectors and capability modules: `backend/connectors/*`, `backend/capabilities/*`, `backend/worker/service.py`
- Frontend routes, pages, hooks, libs, and components: `frontend/src/App.jsx`, `frontend/src/pages/*`, `frontend/src/hooks/*`, `frontend/src/lib/*`, `frontend/src/components/*`

## Important reality about the current system
Runr does not currently have a dedicated analytics event pipeline. Most user analytics must be derived from:

- Relational runtime tables: `runs`, `run_stage_results`, `run_jobs`, `reviews`, `artifacts`, `workers`
- JSON payloads on `users` and `workspaces`
- Artifact metadata generated during CV / cover letter rendering
- Tracker email integration state stored in user metadata

Important caveats:

- `frontend/src/pages/DashboardPage.jsx` is a static preview and does not read real analytics.
- Many frontend interactions are local-state only and are not persisted unless they eventually trigger `PUT /settings`, `POST /runs`, `POST /referrals/...`, `PUT /tracker/...`, or similar writes.
- File-backed persistence mirrors the same logical entities as SQLite, so the analytical shape is the same even when the storage backend changes.

## Status legend

- `Stored`: directly persisted today
- `Derivable`: can be computed from existing persisted state, but is not an explicit event
- `Partial`: some of the signal exists, but important dimensions are missing
- `Missing`: not reliably tracked today

## Current persistent analytical surfaces

- `users.payload_json`
  - `profile`
  - `documents`
  - `candidate_assets`
  - `referrals`
  - `referral_outreach`
  - `external_tracker_applications`
  - job-specific application context, including relevant-people discovery
  - tracker email integration config and sync state
- `workspaces.payload_json`
  - `settings`
  - `feature_flags`
  - `sources`
  - `metadata`
- `runs`
  - lifecycle timestamps, status, attempts, run plan, run metadata
- `run_stage_results`
  - per-stage status, timestamps, metrics, error text, artifact ids
- `run_jobs`
  - normalized jobs by run and job-set
- `reviews`
  - manual review decision plus tracker metadata inside payload JSON
- `artifacts`
  - generated documents, bundle exports, and file metadata
- `workers`
  - worker lease, heartbeat, current run

## 1. USER PROFILE & SEGMENTATION METRICS

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| User registrations | `users.payload_json.created_at` from `UserRecord` persisted through `backend/repositories/sqlite_backed.py` | `COUNT(DISTINCT user_id)` by day/week/month of `created_at` | Stored | HIGH |
| Active account count | `users.is_active`, `users.payload_json.role`, `users.payload_json.allowed_workspace_ids` | `COUNT(DISTINCT user_id)` where `is_active = 1`; segment by role and workspace count | Stored | HIGH |
| Last active date | `MAX(users.updated_at, runs.updated_at, reviews.updated_at, workers.last_heartbeat_at, referral contact updated_at)` per user | Latest persisted timestamp tied to a user | Derivable | HIGH |
| Profile completeness score | `users.payload_json.profile.{name,role_title,email,location,website,linkedin_url,github_url,summary,competencies,languages,recent_experience,education,photo_*}` | Completed core fields / total core fields, weighted if desired | Derivable | HIGH |
| Document readiness score | `users.payload_json.documents`, `users.payload_json.candidate_assets[]` | Weighted score for CV uploaded, photo present, master career profile present, career highlights, bullet bank, memory cards | Derivable | HIGH |
| Onboarding milestone completion | `users.payload_json.profile`, `candidate_assets`, `workspaces`, `runs`, `reviews`, tracker email config, `referrals` | Milestones completed across profile saved, CV uploaded, workspace created, first run, first approved job, tracker connected, first referral contact | Derivable, but no explicit onboarding event stream | HIGH |
| Geography / language segmentation | `users.payload_json.profile.location`, `users.payload_json.profile.languages`, `workspaces.payload_json.settings.country_codes/cities` | User segments by self-described location, language inventory, and target countries/cities | Stored | MEDIUM |
| Candidate seniority / experience richness | `users.payload_json.profile.role_title`, `recent_experience[]`, `education[]` | Bucket by years/record count/title heuristics | Derivable | MEDIUM |
| Job-seeker persona / preference profile | `workspaces.payload_json.settings.{target_roles,keywords,experience_levels,job_filtering_mode,portals,country_codes}` and `users.payload_json.profile.role_title` | Use latest or most-used workspace settings to segment user intent | Derivable | HIGH |
| CV extraction coverage | `POST /cv-upload` and `POST /documents/upload?asset_kind=workspace_cv|master_career_profile` write `parsed_profile`, `profile_extraction`, `source_char_count` into candidate asset metadata | `% of uploads with extracted profile and warning-free parse` | Stored | MEDIUM |
| Display-name / email change history | Only latest `users.email`, `users.payload_json.display_name`, `users.updated_at` | Latest state only | Partial; no change history | LOW |
| Country / locale / UI language | No dedicated account or browser locale persistence beyond free-form profile text | Would require explicit fields | Missing | MEDIUM |
| Plan tier / subscription segment | No billing or plan model in repo | N/A | Missing | HIGH |

## 2. JOB SOURCING & SEARCH BEHAVIOR

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Job sourcing runs started | `runs`, `runs.run_plan_json`, `runs.metadata_json`, `workspaces.workflow_template_id`, `workspaces.payload_json.metadata.automation_flow` | `COUNT(runs)` per user/day/week excluding or including requeues as needed | Stored | HIGH |
| Searches per user per day/week | `runs.user_id`, `runs.created_at`, `runs.metadata.run_kind` | `COUNT(runs)` grouped by user and time grain | Stored | HIGH |
| Source mix by connector / board | `runs.run_plan_json.workspace_snapshot.sources`, `run_jobs.source_type`, `run_jobs.portal`, reusable-package `stage1_source_log` artifact | `% of runs/jobs by source` | Stored | HIGH |
| Filter usage frequency | `workspaces.payload_json.settings.{keywords,target_roles,country_codes,cities,portals,experience_levels,time_posted_seconds,forbidden_title_keywords,low_applicant_threshold}` and run plan snapshots | Count field usage and value frequency across workspaces/runs | Stored | HIGH |
| Jobs returned per search | `run_stage_results.metrics_json.jobs_found`, `run_jobs` per initial sourcing set, `stage1_source_log.total_jobs_collected` | Avg / median / p95 jobs returned per run | Stored | HIGH |
| Screening approval rate | `run_stage_results.metrics_json.approved/rejected` for stage-2 screening | `approved / (approved + rejected)` | Stored | HIGH |
| Prioritization approval rate | `run_stage_results.metrics_json.approved/rejected` for stage-3 prioritization | `approved / (approved + rejected)` | Stored | HIGH |
| Duplicate drop rate | `run_stage_results.metrics_json.dropped_duplicates`, `*_dropped_duplicates` blobs in run data | `dropped_duplicates / (merged_jobs + dropped_duplicates)` | Stored | MEDIUM |
| Quick-apply URL acceptance rate | `runs.metadata.accepted_url_count`, `runs.metadata.invalid_url_count`, `POST /quick-apply/runs` response `invalid_entries` | `accepted / (accepted + invalid)` by user and workspace | Stored | HIGH |
| Manual URL ingestion failure rate | `run_stage_results.metrics_json.failures`, run blob `manual_url_failures`, `backend/capabilities/tailored_documents/workflow.py` output | `failures / (jobs_ingested + failures)` | Stored | MEDIUM |
| Company career-site yield | `run_stage_results.metrics_json.jobs_found/failures`, `company_site_failures` run blob | Jobs found per configured company site | Stored | MEDIUM |
| Portal blocking / hard-stop rate | Reusable-package `stage1_source_log.by_portal.errors`, `backend/connectors/job_boards/collector.py` hard-block logic | Count runs where a portal is stopped early because of 403/429 or similar | Derivable from artifacts, not normalized | HIGH |
| Search keyword patterns | `workspaces.payload_json.settings.keywords`, `target_roles`, `run_plan_json.resolved_run_settings` | Token frequency, co-occurrence, most common query families | Stored | MEDIUM |
| Jobs kept vs dismissed in discovery | Auto stages: `approved/rejected`; human stage: `reviews.payload_json.decision` | Split between auto-kept, auto-rejected, and manually approved/rejected | Partial; no explicit skipped action | HIGH |
| Source-validation error rate before run | `POST /workspace-builder/source-validation` response only; `run.metadata.preflight_error.details.field_errors` only when a run is attempted | Count failed validations by source and field | Partial; ad hoc validation is not persisted unless a run preflight fails | HIGH |
| Career URL discovery usage | `POST /career-url-discovery/run` returns summary, optional file/MySQL outputs only | Count discovery runs and success rate | Missing as persistent product analytics | MEDIUM |

## 3. JOB APPLICATION METRICS

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Total applications submitted | `reviews.payload_json.metadata.application_status`, `reviews.payload_json.metadata.tracker_status`, `users.payload_json.external_tracker_applications[]` | Count applications where normalized status is not `Not applied` | Stored | HIGH |
| Application funnel by status | Same as above, normalized via `normalize_application_status()` | Count by `Applied`, `Interviewing`, `Rejected`, `Offer`, `Withdrawn`, `Unknown` | Stored | HIGH |
| Interview rate | Reviews + external tracker applications | `Interviewing / total applications` | Stored | HIGH |
| Offer rate | Reviews + external tracker applications | `Offer / total applications` | Stored | HIGH |
| Rejection rate | Reviews + external tracker applications | `Rejected / total applications` | Stored | HIGH |
| Application velocity | `application_date`, `applied_at`, `reviews.updated_at`, external tracker app timestamps | Applications per user/day/week and slope over time | Stored | HIGH |
| Time from discovery to application | `runs.created_at` or first job appearance in `run_jobs` vs review/external `application_date` | `application_date - run/job creation timestamp` | Derivable | HIGH |
| Applications by source platform | `run_jobs.portal`, `run_jobs.source_type`, joined to approved/tracked reviews | Count applications by board / source | Stored | HIGH |
| Quick-apply run share | `runs.metadata.run_kind = quick_apply` | `quick_apply runs / all application-oriented runs` | Stored | MEDIUM |
| Requeued-for-generation from rejected jobs | `runs.metadata.requeue_origin.{run_id,job_id,notes}` | Count customized follow-up runs created from rejected/excluded jobs | Stored | MEDIUM |
| Tailored CV generated for an application | `artifacts.metadata_json` / derived document entries with `asset_kind = generated_cv` or applied CV asset kind, linked by `job_id` and `run_id` | `% of applications with a generated CV artifact` | Partial; generation is tracked, actual submitted file choice is not explicit | HIGH |
| Cover letter generated for an application | `artifacts` / document entries with `asset_kind in (cover_letter,motivation_letter)` and related job metadata | `% of applications with generated letter artifacts` | Stored | HIGH |
| Manual apply-link opens | Frontend `ReviewQueuePage.jsx` `applyOnCompanySite()` opens `row.apply_link` only in browser | Count opens | Missing | HIGH |
| Auto-apply vs manual apply ratio | No explicit persisted submission channel or browser automation completion record | N/A | Missing | HIGH |
| Applications per session | No session model | N/A | Missing | MEDIUM |
| Apply-flow abandonment / drop-off | No explicit step events for open link, start form, submit, return | N/A | Missing | HIGH |
| Cover letter edited before sending | Generated asset exists, but no edit history is persisted | N/A | Missing | MEDIUM |

## 4. CV & COVER LETTER CUSTOMIZATION

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| CV customization runs triggered | `run_stage_results.metrics_json.generated_jobs`, requeue runs, `POST /runs/.../excluded-jobs/.../generate-documents` | Count generation runs and generated jobs per run | Stored | HIGH |
| Generated CV artifact count | `artifacts`, document entries with `asset_kind = generated_cv` | `COUNT(documents)` by user/workspace/run | Stored | HIGH |
| Generated cover-letter count | `artifacts`, document entries with `asset_kind in (cover_letter,motivation_letter)` | `COUNT(documents)` by user/workspace/run | Stored | HIGH |
| ATS score distribution | Artifact metadata fields `ats_score`, `ats_best_score`, `ats_target_score`, ATS gate contract | Distribution of best score by document/job/user | Stored | HIGH |
| ATS retry / stall rate | Artifact metadata `ats_attempt_count`, `ats_max_attempts`, `ats_stop_reason`, `ats_attempt_history` | `% target_reached vs max_attempts_reached vs score_stalled` | Stored | HIGH |
| ATS export block rate | ATS gate fields `gate_state`, `can_export_final`, `export_anyway_allowed`; `POST /documents/bulk-export` and `POST /ats/export-gate/evaluate` | `% of docs/exports blocked before override` | Stored | HIGH |
| Document generation failure rate | Generated records contain `doc_generation_error`; stage and artifact metadata preserve failures | `COUNT(doc_generation_error) / COUNT(generated jobs)` | Stored | HIGH |
| PDF conversion failure rate | Generated records contain `pdf_generation_error` | `COUNT(pdf_generation_error) / COUNT(generated jobs)` | Stored | HIGH |
| Template / format adoption | `users.payload_json.documents.{cv_template,cv_color_scheme,cv_font,include_photo,web_cv_template,web_cv_font,web_cv_show_photo,web_cv_palette}` | Count users by current template / option | Stored | MEDIUM |
| Master career profile adoption | `users.payload_json.documents.master_career_profile_asset_id`, candidate assets with `asset_kind = master_career_profile` | `% of active users with a master career profile asset` | Stored | MEDIUM |
| Career-memory builder adoption | `users.payload_json.documents.{generated_memory_cards,career_highlights_text,bullet_bank_text,professional_hurdles_text,motivation_letter_notes,ai_canvas_source_asset_ids}` | Count users with any saved memory-builder output | Stored | MEDIUM |
| CV / cover letter save frequency | `PUT /settings` updates `users.updated_at`, but not section-level change events | Can approximate settings saves, not editor events | Partial | MEDIUM |
| AI suggestion acceptance rate | No explicit accept / reject / regenerate / manual-edit events in CV Studio or Career Memory Builder | N/A | Missing | HIGH |
| Average edits after generation | No document diff, revision history, or edit counters | N/A | Missing | HIGH |
| Most-edited CV sections | No section-level edit persistence | N/A | Missing | HIGH |
| Time spent in CV editor per session | No session timer or focus/blur tracking | N/A | Missing | MEDIUM |

## 5. REFERRAL OUTREACH METRICS

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Referral contacts added | `users.payload_json.referrals[]`, `ReferralContactRecord.created_at/updated_at` | `COUNT(contact_id)` by user and source kind | Stored | HIGH |
| Referral import volume | `BackendApplication.import_referral_contacts()`, `import_batch_id`, `source_kind`, import summary | Contacts imported per batch / user | Stored | HIGH |
| Contact source mix | `ReferralContactRecord.source_kind` | `% manual vs LinkedIn CSV vs enriched` | Stored | MEDIUM |
| Active referable contact count | `ReferralContactRecord.is_active`, `can_refer`, `companies[]` | Count active contacts and active companies with `can_refer = true` | Stored | HIGH |
| Outreach status funnel | `users.payload_json.referral_outreach[run_id::job_id::contact_id].outreach_status` normalized via `normalize_referral_outreach_status()` | Count `Not contacted`, `Contacted`, `Replied`, `Referral offered`, `No referral` | Stored | HIGH |
| Referral reply / referral-offered rate | Same outreach status map | `Replied / Contacted`, `Referral offered / Contacted` | Stored | HIGH |
| Reach-outs per target company | Join outreach-status records to job company and contact company | Count distinct contacts reached per company / run / user | Derivable | MEDIUM |
| Relevant-people discovery activation | `users.payload_json` application context with `relevant_people_discovery.peopleDiscoveryStatus` | Count jobs where discovery is started/completed | Stored | HIGH |
| Saved-for-outreach people count | Relevant-people discovery payload `selectedPeople[].status = saved_for_outreach|confirmed` | Count selected people by category | Stored | MEDIUM |
| Referral draft generation count | `POST /outreach/referral-draft` generates copy but does not persist a draft event | N/A | Missing | HIGH |
| Hiring-manager draft generation count | `POST /outreach/hiring-manager-draft` generates copy but does not persist a draft event | N/A | Missing | HIGH |
| Outreach platform used | Contacts have LinkedIn URLs and user email config exists, but outreach status does not store channel | N/A | Missing | HIGH |
| AI-assisted vs manually written outreach ratio | Message generation exists, but final sent content and manual edits are not persisted | N/A | Missing | HIGH |
| Drafted but not sent drop-off | Draft generation and message-copy actions are not tracked | N/A | Missing | HIGH |
| Delivery / bounce / LinkedIn-limit failures | No sending infrastructure or delivery-event schema in repo | N/A | Missing | MEDIUM |

## 6. FEATURE ADOPTION & ENGAGEMENT

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Active users (proxy) | Any persisted write across `users`, `runs`, `reviews`, `referrals`, tracker sync, artifacts | User is active if any persisted entity changes within day/week/month | Derivable, but not a true session-based DAU/WAU/MAU | HIGH |
| Workspace creation activation | `workspaces` | `% of registered users who created at least one workspace` | Stored | HIGH |
| First-run activation | `runs` | `% of registered users with at least one run` | Stored | HIGH |
| Quick-apply activation | `runs.metadata.run_kind = quick_apply` | `% of users who ever used quick apply` | Stored | HIGH |
| Tracker activation | Tracker email config in user metadata, `/tracker` review updates, external tracker applications | `% of users who connected email or updated tracker state` | Stored | HIGH |
| Referral activation | `referrals[]`, `referral_outreach`, relevant-people discovery | `% of users who added contacts or advanced outreach` | Stored | HIGH |
| Document / export activation | Candidate assets, artifacts, bundle-export documents | `% of users who uploaded documents, generated CVs, or exported bundles` | Stored | HIGH |
| Most-used features ranking | Feature usage proxies from run creation, quick apply, document uploads, bulk export, tracker updates, referrals | Rank features by user count and event count proxy | Derivable | HIGH |
| Least-used features ranking | Same as above | Sort inverse of usage | Derivable | MEDIUM |
| Return after first run | `runs.created_at` per user | `% of users with a second run after first run date` | Stored | MEDIUM |
| Cohort retention by first run / first application | First run date from `runs`; first application date from tracker/reviews | Retention matrix by subsequent activity week | Derivable | HIGH |
| Bulk export usage | Documents with `asset_kind = bundle_export` | Count exports by user/workspace | Stored | MEDIUM |
| Session duration and depth | No page-view/session instrumentation | N/A | Missing | HIGH |
| Return visit rate after first application | No true session/page-return events; can only proxy with later writes | Partial | MEDIUM |
| Page-level feature usage | Frontend routes exist, but no page-view logging | Missing | HIGH |
| Dashboard usage | `DashboardPage.jsx` is mock-only and no page-view is logged | Missing | LOW |

## 7. ERRORS, FAILURES & FRICTION POINTS

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Run failure rate | `runs.status`, `runs.last_error` | `failed runs / total runs` by workflow, workspace, user | Stored | HIGH |
| Stage failure rate | `run_stage_results.status`, `run_stage_results.error` | `failed stages / total stage executions` by stage type | Stored | HIGH |
| Queue retry rate | `runs.attempt_count`, `runs.max_attempts`, run status history via updates | `% of runs with attempt_count > 1` | Stored | MEDIUM |
| Run preflight validation failures | `runs.metadata.preflight_error`, run `last_error` | Count failed runs by error code / field | Stored | HIGH |
| Workspace source-validation friction | `POST /workspace-builder/source-validation` returns `field_errors` and `source_results` but is not persisted | Count validation failures by source / field | Missing as analytics history | HIGH |
| Manual URL ingestion failures | `manual_url_failures` blob, stage metrics `failures` | Count failures by reason and URL source | Stored | HIGH |
| Company-site scrape failures | `company_site_failures` blob, stage metrics `failures` | Count failures by stage (`fetch_company_site`, `discover_company_jobs`, `normalize_company_job`, `dedupe_company_jobs`) | Stored | HIGH |
| Portal scrape / block errors | Reusable-package `stage1_source_log.errors`, portal-specific error strings, 403/429 hard-block logic | Count errors by portal and error pattern | Derivable from artifacts | HIGH |
| Job enrichment errors | `run_jobs.payload_json.enrich_error`, `run_jobs.payload_json.enrich_status_code`, LinkedIn/manual enrichment outputs | Error rate by board and status code | Stored | HIGH |
| Document generation failures | Generated document records `doc_generation_error`; stage 4 results | Count failures by model, workspace, job, template | Stored | HIGH |
| PDF conversion failures | Generated document records `pdf_generation_error` | Count failures by renderer/workspace/job | Stored | HIGH |
| ATS gate blocks | ATS gate contract and artifact metadata | Count blocked exports and stalled scoring loops | Stored | HIGH |
| Tracker email authorization failures | Tracker email config `last_error`, `authorization_state`, `connected` | Count auth failures and reauthorization-required states | Stored | HIGH |
| Tracker sync failures | Tracker email config `last_error`, sync results, `pending_detections`, `last_sync_summary` | Count sync failures and unresolved detection backlog | Stored | HIGH |
| People-discovery failures | Relevant-people discovery payload `peopleDiscoveryStatus = failed`, `error` | Count discovery failures by user/job/company | Stored | MEDIUM |
| CV upload / parse failures | Upload routes return errors, but failures are not persisted when the request fails | N/A | Missing | HIGH |
| Profile photo upload failures | Request fails return errors only | N/A | Missing | LOW |
| Repeated form validation errors on same field | Only latest responses are shown client-side; no analytics log | N/A | Missing | MEDIUM |
| API 4xx / 5xx rate by route | Server returns structured errors, but no centralized request log table exists | N/A | Missing | HIGH |
| Support ticket correlation | No support domain or ticket schema in repo | N/A | Missing | MEDIUM |

## 8. CONVERSION & MONETIZATION SIGNALS

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Last active date / churn-risk proxy | Same last-active inputs from section 1 | Days since last persisted activity | Derivable | HIGH |
| First-value proxy: first application tracked | First review/external tracker record with application status not `Not applied` | Days from registration to first tracked application | Derivable | HIGH |
| First-value proxy: first document export | Bundle-export asset or generated CV/cover-letter artifact | Days from registration to first export | Derivable | MEDIUM |
| ATS gate override usage | `POST /documents/bulk-export` with `export_anyway`, ATS gate `exported_anyway` state | Count exports that required override | Stored | MEDIUM |
| Export bundle creation rate | Documents with `asset_kind = bundle_export` | Exports per user and export adoption rate | Stored | MEDIUM |
| High-intent behavior score | Composite from first run, first quick apply, first tracker connection, first referral contact, first export | Weighted composite | Derivable | MEDIUM |
| Plan tier | No billing/subscription model | N/A | Missing | HIGH |
| Free-tier limits hit | No quota or entitlement schema is present | N/A | Missing | HIGH |
| Upgrade prompt shown / clicked / converted | No paywall / upgrade prompt instrumentation exists | N/A | Missing | HIGH |
| Time to upgrade | No plan-change history exists | N/A | Missing | HIGH |
| Upgrades / downgrades / cancellations | No subscription lifecycle entity exists | N/A | Missing | HIGH |
| Feature in use at moment of upgrade | No billing event stream exists | N/A | Missing | HIGH |

## 9. PIPELINE & OUTCOME TRACKING

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Pipeline stage distribution per user | `reviews.payload_json.metadata.application_status`, `users.payload_json.external_tracker_applications[]` | Count applications in each status bucket | Stored | HIGH |
| Interview rate | Same as above | `Interviewing / total applications` | Stored | HIGH |
| Offer rate | Same as above | `Offer / total applications` | Stored | HIGH |
| Withdrawal rate | Same as above | `Withdrawn / total applications` | Stored | MEDIUM |
| Rejection rate | Same as above | `Rejected / total applications` | Stored | HIGH |
| Applied-to-rejected time | `application_date` or `applied_at` vs `rejected_at` | Avg / median days to rejection where both timestamps exist | Partial; timestamps are sparse and mostly rejection-focused | MEDIUM |
| Email-confirmed application share | `reviews.payload_json.metadata.email_confirmed`, Gmail sync results | `% of applications confirmed by inbox evidence` | Stored | MEDIUM |
| External-inbox-detected applications | `users.payload_json.external_tracker_applications[]`, Gmail detections | Count applications discovered from inbox, including those not tied to a Runr run | Stored | MEDIUM |
| User-reported notes / outcome annotations | `reviews.notes`, `reviews.payload_json.metadata.notes`, external application notes | Count annotated applications and common note themes | Stored | LOW |
| Rejected-job reason mix | Rejected job blobs normalized through `normalize_rejected_job_review()` and server reason mapping | Count `keyword_mismatch`, `seniority_mismatch`, `language_mismatch`, `location_mismatch`, `duplicate`, `source_validation_failed`, `manual_rejection`, `unknown` | Stored | HIGH |
| Job found through Runr confirmation | No explicit boolean tying a final outcome to Runr discovery exists | N/A | Missing | HIGH |
| Time in each stage | No dedicated `interview_started_at`, `offer_at`, `withdrawn_at` timestamps are maintained | N/A | Missing | HIGH |

## 10. INFRASTRUCTURE & SYSTEM EVENTS

| Metric name | Data source | Calculation | Current status | Priority |
| --- | --- | --- | --- | --- |
| Queued runs per user | `runs.status`, `runs.queued_at`, `runs.user_id` | Count queued runs and queue backlog by user/workspace | Stored | HIGH |
| Queue wait time | `runs.started_at - runs.queued_at` | Avg / p95 queue latency | Stored | HIGH |
| Run processing time | `runs.finished_at - runs.started_at` | Avg / p95 execution duration by workflow and stage mix | Stored | HIGH |
| Stage processing time | `run_stage_results.finished_at - started_at` | Avg / p95 duration by stage type | Stored | HIGH |
| Retry rate | `runs.attempt_count`, `runs.max_attempts` | % runs retried; average attempts per failed run | Stored | MEDIUM |
| Worker heartbeat freshness | `workers.last_heartbeat_at`, `workers.lease_expires_at`, `workers.status` | Stale worker count and heartbeat age | Stored | HIGH |
| Stale-worker recovery count | `POST /workers/recover-stale`, recovered workers, `runs.last_error = Recovered from expired worker lease.` | Count recoveries by worker and run | Stored | MEDIUM |
| Worker utilization | `workers.current_run_id`, `workers.status`, run timestamps | Share of workers busy vs idle, plus run ownership | Stored | MEDIUM |
| Portal rate-limit / blocked events | Portal source logs and connector error strings with `403`, `429`, blocked portal note | Count blocked portal combinations per run/user | Derivable from artifacts | HIGH |
| Proxy fallback usage | Workspace setting `use_proxy_fallback`; enrichment attempt chains in `enrich_error` and connector traces | Count runs/jobs where proxy fallback was enabled or apparently used | Partial; stored mostly as free text | MEDIUM |
| Gmail sync volumes | Tracker email config `processed_message_ids`, `last_sync_summary`, `last_sync_at` | Messages processed, detections created, reviews updated per sync | Stored | HIGH |
| Gmail pending-review backlog | Tracker email config `pending_detections`, `last_sync_summary.pending_review` | Backlog count per user | Stored | HIGH |
| Career URL discovery throughput | `/career-url-discovery/run` returns `processed`, `found`, `not_found`, `saved_list_path`, but no durable per-user run record | N/A | Missing | MEDIUM |
| OAuth callback volume / authorization funnel | Google callback route exists, but no analytics event is written | N/A | Missing | LOW |
| Webhook events received and processed | No general webhook/event-ingestion subsystem exists in repo | N/A | Missing | LOW |

## GAPS & INSTRUMENTATION NEEDED

### Recommended base schema
Add one append-only table for cross-product analytics:

`analytics_events`

- `event_id TEXT PRIMARY KEY`
- `event_name TEXT NOT NULL`
- `occurred_at TEXT NOT NULL`
- `user_id TEXT`
- `session_id TEXT`
- `workspace_id TEXT`
- `run_id TEXT`
- `job_id TEXT`
- `review_id TEXT`
- `route TEXT`
- `source TEXT`
- `payload_json TEXT NOT NULL`

Recommended indexes:

- `(event_name, occurred_at)`
- `(user_id, occurred_at)`
- `(workspace_id, occurred_at)`
- `(run_id, occurred_at)`
- `(job_id, occurred_at)`

Add a dedicated subscription table when billing exists:

`subscription_events`

- `subscription_event_id TEXT PRIMARY KEY`
- `user_id TEXT NOT NULL`
- `occurred_at TEXT NOT NULL`
- `event_type TEXT NOT NULL`
- `plan_id TEXT`
- `previous_plan_id TEXT`
- `billing_provider TEXT`
- `payload_json TEXT NOT NULL`

### Event gaps to add now

| Gap | Event to log | Payload fields | Where to add the logging call | Table/schema change needed |
| --- | --- | --- | --- | --- |
| No true DAU/WAU/MAU or page usage | `session_started`, `page_view` | `session_id`, `route`, `referrer`, `user_agent`, `viewport`, `workspace_id`, `run_id`, `job_id` | Frontend route layer in `frontend/src/App.jsx`; connection-aware wrapper in `frontend/src/context/SessionContext.jsx`; optional `POST /analytics/events` endpoint | Add `analytics_events` |
| No onboarding funnel | `onboarding_step_completed` | `step_id`, `step_name`, `completion_source`, `workspace_id`, `asset_id` | Server-side after successful writes in `backend/api/server.py:4732-4801` (`cv-upload`), `4803-4835` (`profile-photo-upload`), `5168-5173` (`workspace-builder/workspaces`), `5194-5235` (`runs`), plus `PUT /settings` at `5560-5582` | Add `analytics_events` |
| No persistent log of source-validation friction | `workspace_source_validation_failed`, `workspace_source_validation_passed` | `source_ids`, `field_errors`, `source_results`, `workspace_payload_hash` | `backend/api/server.py:5175-5177` (`POST /workspace-builder/source-validation`) | Add `analytics_events` |
| No workspace configuration history | `workspace_saved` | `workspace_id`, `automation_flow`, `source_ids`, `keywords`, `target_roles`, `country_codes`, `portals`, `cv_generation_mode` | `backend/api/server.py:5168-5173` and `5602-5615` | Add `analytics_events` |
| No explicit search event | `job_search_requested`, `job_search_completed` | `workspace_id`, `run_id`, `execution_mode`, `source_ids`, `filters`, `jobs_found`, `approved`, `rejected`, `dropped_duplicates`, `status` | Request at `backend/api/server.py:5194-5235`; completion inside `backend/orchestration/engine.py` after stage execution and/or in `backend/application/services.py::_execute_run` | Add `analytics_events` |
| No apply-flow funnel | `apply_link_opened`, `application_submission_confirmed`, `application_submission_abandoned` | `run_id`, `job_id`, `review_id`, `apply_link`, `source_type`, `portal`, `cv_asset_kind`, `cover_letter_included` | Frontend `frontend/src/pages/ReviewQueuePage.jsx:373-384` browser-open action; manual confirmation in `markApplied()` at `346-356`; tracker status updates at `backend/api/server.py:5677-5758` | Add `analytics_events` |
| No auto-apply vs manual-apply attribution | `application_channel_set` | `run_id`, `job_id`, `review_id`, `channel` (`manual_link`, `quick_apply`, future `auto_apply`), `source` | In `ReviewQueuePage.jsx` when user opens company-site link or marks applied; in `POST /quick-apply/runs` at `5120-5166` | Add `analytics_events` and optionally `reviews.payload_json.metadata.application_channel` |
| No CV-generation request/completion events | `cv_generation_requested`, `cv_generation_completed`, `cv_generation_failed` | `workspace_id`, `run_id`, `job_id`, `source_stage`, `reason_summary`, `generated_jobs`, `artifact_ids`, `error` | `frontend/src/pages/JobWorkspacePage.jsx:440-476`; backend `POST /runs/.../excluded-jobs/.../generate-documents` at `5288-5307`; stage completion in `backend/adapters/stage_adapters.py` stage-4 metrics | Add `analytics_events` |
| No cover-letter generation event | `cover_letter_generated` | `run_id`, `job_id`, `artifact_id`, `template`, `ats_best_score`, `ats_gate_state` | When artifacts are persisted during stage-4 document rendering, plus document listing builder in `backend/api/server.py` | Add `analytics_events` |
| No CV editor / memory builder interaction data | `cv_editor_saved`, `career_memory_saved`, `memory_card_generated`, `memory_card_deleted` | `changed_fields`, `memory_card_count`, `asset_ids`, `template`, `font`, `palette` | Frontend `frontend/src/pages/CvStudioPage.jsx`, `frontend/src/pages/ArtifactsPage.jsx:435-467`, and `frontend/src/components/careerMemoryBuilder/*` just before `PUT /settings` | Add `analytics_events` |
| No referral draft-generation metrics | `referral_draft_generated`, `hiring_manager_draft_generated`, `draft_copied` | `run_id`, `job_id`, `contact_id`, `company`, `channel`, `message_length`, `used_ai = true` | Backend `backend/api/server.py:4994-5015`; frontend composer copy action in `frontend/src/pages/ReviewQueuePage.jsx:467-476` | Add `analytics_events` |
| Outreach status lacks channel/send metadata | `outreach_status_changed` | `run_id`, `job_id`, `contact_id`, `previous_status`, `next_status`, `channel`, `message_origin`, `sent_at` | Backend `backend/api/server.py:4987-4992` and `5584-5589`; frontend `persistOutreachStatus()` in `frontend/src/pages/ReviewQueuePage.jsx:237-275` and `ReferralsPage.jsx` | Add `analytics_events`; extend outreach-status payload/schema to include `channel` and optional `message_origin` |
| No AI-vs-manual outreach ratio | `outreach_message_composed` | `run_id`, `job_id`, `contact_id`, `composer_mode`, `origin` (`ai_generated`, `manual`), `edited_after_generation` | Frontend draft composer in `ReviewQueuePage.jsx` and future referrals composer | Add `analytics_events` |
| No people-discovery usage funnel | `people_discovery_started`, `people_discovery_completed`, `people_discovery_failed`, `relevant_person_status_changed` | `run_id`, `job_id`, `company`, `category_counts`, `warnings_count`, `error`, `person_id`, `status` | Backend `backend/api/server.py:5236-5287`; application methods in `backend/application/services.py:1055-1139` | Add `analytics_events` |
| No document-upload and parse-failure analytics | `document_uploaded`, `document_upload_failed`, `cv_parsed`, `cv_parse_failed`, `profile_photo_uploaded`, `profile_photo_upload_failed` | `asset_kind`, `filename`, `mime_type`, `char_count`, `warning_count`, `workspace_id`, `error_code` | Backend `backend/api/server.py:4680-4835` | Add `analytics_events` |
| No tracker-sync event stream | `tracker_sync_started`, `tracker_sync_completed`, `tracker_sync_failed`, `gmail_detection_reviewed` | `provider_id`, `scan_window`, `max_messages`, `messages_processed`, `detections`, `updated_reviews`, `pending_review`, `error`, `approval_state` | Backend `backend/api/server.py:4848-4967`, `5398-5511`, `5622-5675`; logic in `backend/capabilities/tracker/email_integration.py` | Add `analytics_events` |
| No export funnel | `ats_gate_evaluated`, `export_bundle_requested`, `export_bundle_completed`, `export_bundle_blocked` | `document_ids`, `best_score`, `attempt_count`, `gate_state`, `export_anyway`, `bundle_id` | Backend `backend/api/server.py:4840-4847` and `5183-5192`; frontend export flow in `frontend/src/pages/ArtifactsPage.jsx:502-510` and `TrackerPage.jsx:402-410` | Add `analytics_events` |
| No centralized request/error telemetry | `api_request_completed`, `api_request_failed` | `route`, `method`, `status_code`, `error_code`, `latency_ms`, `user_id` | Shared HTTP handler in `backend/api/server.py`; easiest around `_send_json()` / `_send_error()` or request dispatch boundaries | Add `analytics_events` or a separate `api_request_logs` table |
| No career-URL-discovery analytics | `career_url_discovery_run_completed`, `career_url_discovery_run_failed` | `source`, `limit`, `offset`, `use_rendered_fallback`, `save_mysql`, `processed`, `found`, `not_found`, `saved_list_path`, `error` | Backend `backend/api/server.py:5050-5084`; frontend trigger in `frontend/src/pages/CareerUrlDiscoveryPage.jsx:37-57` | Add `analytics_events` |
| No monetization instrumentation | `paywall_impression`, `upgrade_clicked`, `subscription_changed`, `subscription_cancelled`, `limit_hit` | `plan_id`, `previous_plan_id`, `limit_type`, `usage`, `quota`, `surface` | Future billing/prompt surfaces; no current insertion point because the product codebase has no billing module | Add `subscription_events`; optionally add `users.payload_json.plan_id` for current state |

## RECOMMENDED ANALYTICS DASHBOARD VIEWS

1. **Acquisition To Application Funnel**
   - Users registered
   - CV uploaded
   - Workspace created
   - First run started
   - Jobs approved
   - First tracked application
   - First interview
   - First offer

2. **Job Sourcing Quality Dashboard**
   - Runs by source mix
   - Jobs found per run
   - Screening approval rate
   - Prioritization approval rate
   - Duplicate drop rate
   - Portal block/error rate
   - Quick-apply URL acceptance rate

3. **Document Generation & ATS Health**
   - Generated CV count
   - Cover-letter count
   - ATS best-score distribution
   - ATS stop-reason mix
   - Export blocked vs exported-anyway
   - Doc generation and PDF failure rates

4. **Pipeline Outcomes Dashboard**
   - Application status distribution
   - Interview, rejection, offer, and withdrawal rates
   - Applied-to-rejected time where available
   - Internal Runr-tracked vs external inbox-detected applications
   - Rejection-reason mix for sourced jobs

5. **Referral & Tracker Engagement Dashboard**
   - Referral contacts added/imported
   - Active referable contacts
   - Outreach status funnel
   - Relevant-people discovery activation
   - Tracker email connection rate
   - Gmail sync success/failure and pending-review backlog

## Bottom line
Runr already stores enough operational state to answer many high-value questions about sourcing throughput, document-generation quality, application outcomes, referral inventory, and tracker status progression.

What it does not yet store is the event layer needed for:

- real DAU / WAU / MAU
- apply-flow drop-off
- CV / outreach edit behavior
- onboarding step-by-step conversion
- page and session engagement
- monetization / subscription analytics

If you add the single `analytics_events` table plus the 15-20 events above, Runr moves from "mostly reconstructable operational analytics" to a proper product analytics stack.
