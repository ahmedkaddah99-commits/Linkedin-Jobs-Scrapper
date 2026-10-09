> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Career profiles, CV and documents (WS-4, secondary)

This doc is a slice of [personalized-jobs-and-customer-app-services.md](personalized-jobs-and-customer-app-services.md) (the primary). The primary holds the full owned-path table, the env-key table, the Render/renderer dependency, the registry proposal and the shared gaps. The browser-extension side of Assisted Apply is WS-9: [assisted-apply.md](assisted-apply.md).

All references are to `58a96674`, read statically. Nothing was run. LIVE PRODUCTION = UNKNOWN.

## 1. Purpose and user-facing capabilities

| Capability | Main code (owned) |
|---|---|
| Career profiles bound to a workspace and a baseline CV, rebind review, baseline CV replacement | `backend/application/rebind_service.py`, `backend/application/baseline_cv_replacement_service.py`; persistence via `career_profile_store` (WS-5: `SqliteCareerProfileStore` `backend/repositories/sqlite_backed.py:2847`, `FileCareerProfileStore` `backend/repositories/file_backed.py:1153`) |
| CV upload and extraction (PDF/DOCX/PPTX/images → text → structured profile) | `backend/profiles/cv_upload_jobs.py`, `document_text.py`, `cv_profile_extraction.py`, `gemini_extraction.py`, `deepseek_extraction.py`, `extraction_schema.py`; `backend/capabilities/source_processing/**` |
| Workspace CV editor (structured edit, DOCX regeneration, revision conflict) | `backend/profiles/cv_editor.py` |
| Master CV (single editable CV document with entries/bullets, export, bullet selection) | `backend/master_cv/service.py` |
| Canonical Career Evidence: extract, review/confirm, questions, readiness, outputs | `backend/capabilities/candidate_evidence/**`, `backend/evidence/review_service.py`, `backend/evidence/question_service.py` |
| Profile-scoped evidence items and links to experiences | `backend/evidence/service.py` |
| Evidence library (beyond CV bullet limits) | `backend/evidence_library/service.py` |
| Work-experience timeline, extraction, merge suggestions | `backend/work_experience/service.py` |
| CV bullet suggestions, evidence recommendations, source text review, career-profile evidence lifecycle | `backend/capabilities/{cv_bullet_suggestions,evidence_recommendation,source_text_review,career_profile_evidence}/**` |
| Job application bindings (requirements analysis per profile) | `backend/capabilities/profile_matching/application_binding.py` |
| Tailored CV / cover letter / motivation letter generation and rendering (run stages) | `backend/capabilities/tailored_documents/**` (21 files) |
| Legacy Career Memory | `backend/career_memory/service.py` (no runtime importer, §5) |
| Local tools | `backend/tools/**` |

## 2. Owned paths and governing instructions

| Path | Files |
|---|---|
| `backend/profiles/` | 11 (incl. `baseline_cv_reusable_packages.txt`) |
| `backend/master_cv/` | 2 |
| `backend/career_memory/` | 2 |
| `backend/evidence/` | 4 |
| `backend/evidence_library/` | 2 |
| `backend/work_experience/` | 2 |
| `backend/tools/` | 6 |
| `backend/capabilities/tailored_documents/`, `candidate_evidence/`, `career_profile_evidence/`, `cv_bullet_suggestions/`, `evidence_recommendation/`, `source_processing/`, `source_text_review/`, `profile_matching/`, `reusable_packages/` | 21, 6, 2, 2, 2, 4, 2, 2, 7 |
| `backend/application/baseline_cv_replacement_service.py`, `backend/application/rebind_service.py` | 2 |
| `backend/repositories/document_payloads.py` | 1 |

Governing docs: root `AGENTS.md` (Python environment only). Related reports, historical and not re-verified: `docs/reports/ai_document_catalog_2026-05-27.md`, `docs/reports/cv_export_pdf_preview_bullets_fix_report_2026-05-28.md`, `docs/reports/cv_language_section_parser_report_2026-05-30.md`. Ticket IDs in module docstrings (CP-007 … CP-044R) are the historical lineage (§8). No CP ticket spec was found under `docs/` at baseline.

## 3. Entry points and registered routes

Every route module below is registered in `build_route_registry` (`backend/api/routes/__init__.py`). The only exception is `career_evidence_fixture.py` (§10). Route handlers are owned by WS-1 ([backend-api.md](../01-architecture/backend-api.md)).

| Route module | Registered names | Owned code called |
|---|---|---|
| `backend/api/routes/career_profiles.py:25-57` | `career_profiles.list/create/get/update/delete`, `.bind/unbind`, `.bind_baseline_cv/unbind_baseline_cv`, `.rebind_review/rebind_confirm`, `.baseline_cv_replacement_preview/confirm` | `rebind_service.perform_rebind_compatibility_review` (L329) / `execute_rebind` (L356); `baseline_cv_replacement_service.preview_baseline_cv_replacement` (L403) / `confirm_baseline_cv_replacement` (L452) |
| `backend/api/routes/master_cv.py:32-43` | `master_cv.get/update/export/tailor`, `.entries.create/update/delete`, `.bullets.create/update/delete/guidance/improve` | `master_cv/service.py` (`get_document` L310, `persist_document` L539, `export_document` L519, `select_relevant_bullets` L459) |
| `backend/api/routes/documents.py:77-87` | `documents.cv`, `.cv_upload_status`, `.cv_upload`, `.profile_photo_upload`, `.documents*`, `.ats`, `.run_generation`, `.contracts` | `profiles/cv_upload_jobs.enqueue_cv_upload_processing_run` (L309, L404), `profiles/cv_editor.build_cv_editor_payload`/`save_cv_editor_asset` (editor at L96, L602; sections L663), `profiles/document_text.extract_document_text`, bulk export task (see primary) |
| `backend/api/routes/evidence_items.py:46-68` | `evidence_items.*` (next-review, readiness, ready-actions, journey-state, review-action, clear-spikes, confirm-inspect, answer-enrich, skip-question, get/post/put) | `capabilities/candidate_evidence`, `evidence/review_service.py`, `capabilities/source_processing` |
| `backend/api/routes/evidence_questions.py:28-48` | `evidence_questions.get/answer/skip/dismiss/recalculate/history` | `evidence/question_service.py` |
| `backend/api/routes/career_evidence.py:15-37` | `career_evidence.list/create/get/update/delete`, `.links.list/create/confirm/dismiss`, `.suggest_links/suggest_all` | `evidence/service.py` |
| `backend/api/routes/evidence_library.py:16-44` | `evidence_library.list/create/get/update/delete` | `evidence_library/service.py` |
| `backend/api/routes/work_experiences.py:20-38` | `work_experiences.list/create/get/update/delete/extract/merge_suggestions/confirm_merge/dismiss_merge` | `work_experience/service.py` |
| `backend/api/routes/cv_bullet_suggestions.py:31-60` | `cv_bullet_suggestions.generate/list/get/action/accepted` | `capabilities/cv_bullet_suggestions` |
| `backend/api/routes/evidence_recommendation.py:17-31` | `evidence_recommendation.generate/get/set_match_status` | `capabilities/evidence_recommendation` |
| `backend/api/routes/source_text_review.py:21-46` | `source_review.get/update/confirm/reject/list/verified_texts` | `capabilities/source_text_review` |
| `backend/api/routes/career_profile_evidence.py:26-61` | `career_profile_evidence.list/get/verify/reject/defer/edit` | `capabilities/career_profile_evidence` |
| `backend/api/routes/application_bindings.py:20-32` | `application_bindings.list/create/get/delete` | `capabilities/profile_matching/application_binding.py` |
| `backend/api/routes/motivation_letters.py:26` | `motivation_letters.generate` | `capabilities/tailored_documents/motivation_letters.py` (`DEEPSEEK_API_KEY` read in route, L21-22) |
| `backend/api/routes/career_memory.py:16-17` | `career_memory.get` (read-only compatibility view from `candidate_evidence` metadata), `career_memory.post` (**410 Gone**, "use /evidence-items") | none; does not import `backend/career_memory` |
| `backend/api/routes/evidence.py:22-50` | `evidence.list_states/list/create/get/update/transition/history/delete` | WS-5 `backend/domain/evidence.py` only; no WS-4 module |

Worker / stages ([backend-workers-and-orchestration.md](../01-architecture/backend-workers-and-orchestration.md)):
- CV upload processing is a run. `enqueue_cv_upload_processing_run` (`cv_upload_jobs.py:114`, system workspace `__cv_upload__` L28) creates it; the customer worker claims it, and `run_services.py:771-772` routes it to `process_cv_upload_run` (L334).
- Tailored document stages are registered in `backend/adapters/stage_adapters.py:1206+`: `TailoredScreeningStage` L882, `TailoredPrioritizationStage` L902, `TailoredDocumentExportStage` L972, `SourceProcessingStage` L1174 and the reusable-package stages L1054-1142. They call `capabilities/tailored_documents/{acquisition,screening,prioritization,documents,workflow,runtime}` and `capabilities/reusable_packages/*`.

CLI tools (not wired into deploy units):

| Tool | Use |
|---|---|
| `backend/tools/discover_company_careers.py` | career URL discovery (MySQL store `MySqlCareerDiscoveryConfig.from_env()` L865). Imported by `workspace_runner.py:15` and `backend/api/server.py:116`; the API route is disabled (primary §3.1). Test: `tests/test_company_career_discovery.py` |
| `backend/tools/merge_career_discovery_shards.py` | merges discovery shards |
| `backend/tools/build_test_cv_bundle.py`, `backend/tools/build_test_cv_web_templates.py` | generate sample CV bundles/templates into a local `test CV/` folder |
| `backend/tools/dump_run_diagnostics.py` | run diagnostics dump |
| `backend/scripts/migrate_users_to_clerk.py` | one-off user migration to Clerk (WS-6 integration) |

## 4. Inputs, outputs, storage and dependencies

- **Where state lives:**
  - User metadata (via `auth_repository.upsert_user`): Master CV `master_cv` (`master_cv/service.py:25,539-546`), canonical evidence `candidate_evidence`/`evidence_outputs` (read at `career_memory.py` route), question history `evidence_question_history` (`question_service.py:67`), review cursor `evidence_review_cursor` (`review_service.py:48`).
  - Career-profile metadata: `evidence_items`/`evidence_links` (`evidence/service.py:25-26`), `evidence_library` (`evidence_library/service.py:25`), `work_experiences`/merge suggestions (`work_experience/service.py:31-32`), `application_bindings` (`application_binding.py:38`).
  - Candidate documents: `candidate_assets`/`candidate_documents` tables (`sqlite_migrations.py:585,598`, migration `013_candidate_document_normalization`). `backend/repositories/document_payloads.py` splits text/asset fields out of user/workspace/run payloads (`prepare_user_payload` L23, `prepare_workspace_payload` L96, `prepare_run_payload` L144); it is used by `sqlite_backed.py` and `sqlite_migrations.py` (WS-5).
  - Career profiles: migrations `021`–`026` (WS-5 [schema-and-migrations.md](../03-data/schema-and-migrations.md)).
  - Uploaded bytes and generated DOCX/PDF go to object storage (`cv_upload_jobs.py` `object_storage.get`, `cv_editor.py` `build_private_object_key`; WS-5 [object-storage-r2.md](../03-data/object-storage-r2.md)).
- **In-memory module stores (not persisted):** `_suggestions` (`capabilities/cv_bullet_suggestions/service.py`), `_evidence_store` (`capabilities/career_profile_evidence/service.py`), `_reviews` (`capabilities/source_text_review/service.py`), `_recommendations` (`capabilities/evidence_recommendation/service.py`). See WS4-G7.
- **AI/LLM providers** (key names only):
  - Gemini `gemini-2.5-flash-lite` via `google.genai` for multimodal OCR/extraction (`profiles/gemini_extraction.py:30,63-78`, key `GEMINI_API_KEY`/`GOOGLE_API_KEY` via `env_schema.get_env`).
  - Fallback chain Gemini → DeepSeek → local text (`capabilities/source_processing/extraction.py:109-142`).
  - DeepSeek `https://api.deepseek.com/chat/completions` with `DEEPSEEK_API_KEY` in: `profiles/deepseek_extraction.py:74-90` (`DEEPSEEK_SOURCE_MODEL`), `profiles/cv_profile_extraction.py:976,1003-1004` (`DEEPSEEK_CV_PROFILE_MODEL`), `capabilities/tailored_documents/generation.py:341-392` (`DEEPSEEK_STAGE4_MODEL` via `documents.py:317`), `motivation_letters.py:671`, `title_filter.py:92-93`, `reusable_packages/classification.py:194-248`, and `linkedin_connector.py:189` (also `SCRAPEOPS_API_KEY` L171).
  - `DEEPSEEK_API_KEY` is declared in `render.yaml` (L152, L241); `GEMINI_API_KEY` is only in `env_schema.py` (see the primary §4).
- **Legacy/local env inputs:** `MY_CV_PATH`, `MY_CV_SUMMARY` (`profiles/cv_text.py:119,133`; `rendering.py:339`) fall back to a local `user_config/cv_master.txt` (`cv_text.py:13`). The hard-coded fallback strings in `cv_text.py:15` and `profiles/reusable_packages.py:6` are single-candidate residue (WS4-G9). `STAGE1_*`/`STAGE4_*` tuning keys are in `tailored_documents/acquisition.py:50-115` and `documents.py:341-378`.
- **Rendering:** DOCX via python-docx (`rendering.py:368 create_cv_document`, `cv_editor.py:228 create_cv_docx_bytes`). PDF via `node frontend/scripts/render-cv-pdf.mjs` fed by `build_cv_html_export_payload` (`rendering.py:1254,1336-1380`, 45 s timeout), which depends on `frontend/src/lib/cvStudio.js` and `frontend/src/lib/cvSocialLinks.js`. These are the 5 frontend paths in the Render api/worker `buildFilter` (`render.yaml:60-64,176-180`), owned by WS-7 ([render.md](../02-deployment/render.md)). Excel tracker export uses `tracker_export.py:194 save_to_excel`.

## 5. Important call/data flows

1. **CV upload:**
   - `POST cv-upload` (`documents.py:337`) stores the bytes and calls `enqueue_cv_upload_processing_run` → the worker runs `process_cv_upload_run` (`cv_upload_jobs.py:334`).
   - Asset status moves `uploaded → queued → processing → ready|failed` (L31-36). A `ready` asset that already has `source_text` is skipped.
   - Processing: `object_storage.get` → `capabilities/source_processing/extraction.process_source_bytes` (Gemini → DeepSeek → local) → `extract_cv_profile` (DeepSeek, or the regex fallback `extract_cv_profile_fallback` L858) → a Word companion for non-DOCX files (`document_text.create_word_companion_bytes` L328).
   - The client polls `GET cv-upload/{id}` (`documents.py:142`).
2. **CV editor:** `GET documents/assets/{id}/editor` → `build_cv_editor_payload` (`cv_editor.py:136`). The PUT path (`documents.py:602`) calls `save_cv_editor_asset` (L373), which rejects a stale `base_revision` with `CvEditorRevisionConflict` (L75), keeps ≤12 history entries (L18), regenerates DOCX and stores a private object key.
3. **Master CV:**
   - `get_document` builds the initial document from the user (`build_initial_document` L277).
   - Mutations go through `add/update/delete_entry|bullet` and then `persist_document` into user metadata. Limits: 4000 chars, 100 bullets/entry, 100 entries/section (L27-29).
   - `master-cv/tailor` is deterministic bullet ranking (`select_relevant_bullets` L459); no LLM call. `improve_bullet` (L445) is also local.
4. **Canonical evidence journey** (`evidence-items`):
   - `run_evidence_pipeline` (`candidate_evidence/__init__.py:47`) extracts from verified sources (`extraction.py:111`), then dedupes and detects conflicts.
   - Review uses `review_service.get_next_review_item` (L389), `confirm_evidence` (L438), `confirm_with_inspect` (L633), `answer_enrich_evidence` (L751) and `compute_canonical_readiness` (L541).
   - Questions come from `question_service.select_next_question` (L236), using missing-detail types at L37-43.
   - Outputs come from `generate_evidence_outputs` (`generation.py:148`).
   - Legacy Career Memory facts are migrated by `migration.migrate_legacy_facts_to_evidence` (L70) and `clear_legacy_career_memory` (L165).
5. **Baseline CV replacement:** `preview_baseline_cv_replacement` diffs experiences and bullets (similarity thresholds 0.25, L28-29). `confirm_baseline_cv_replacement` (L452) validates that the preview belongs to the profile and is not stale, then updates only the baseline CV binding while preserving evidence/provenance/history (docstring L458-462). The rebind review uses similarity 0.45 and conflict 0.70 (`rebind_service.py:117-118`).
6. **Tailored documents in runs:**
   - `TailoredDocumentExportStage` → `documents.run_standard_cv_pipeline` (L231).
   - `generation.build_docs_prompt` (L119) → `call_ai_json` (L373, DeepSeek) → ATS score/improvement prompts (L233, L269).
   - Then `cv_structuring.ensure_structured_cv_fields` (L777), `provenance.propagate_tailored_provenance` (L32), and finally `rendering.create_cv_document` / `create_cv_pdf_document`.
   - Assisted Apply packages consume these artifacts (primary §5.5).
7. **Motivation letters:** `generate_motivation_letter_for_job` (`motivation_letters.py:376`) → `assess_evidence_sufficiency` (L183) → structured prompt (L320) → DeepSeek → `validate_letter_claims` (L442) and `validate_section_evidence_refs` (L454).

## 6. Invariants, failure handling and recovery

- Rejected or unverified evidence is excluded from generated material (`career_profile_evidence/service.py` docstring; `evidence_recommendation/service.py` filters on `EVIDENCE_STATUS_CONFIRMED`).
- Letter claims are checked against the CV and job text to catch copied or invented text (`motivation_letters.py:442-454`).
- CV editor optimistic concurrency via `base_revision` (`cv_editor.py:392-395`).
- Master CV normalisation on persist (`master_cv/service.py:539-546`). Structural errors map to 422 in the route (`master_cv.py:99-100`).
- Provider failures fall back instead of failing the upload: Gemini failure → DeepSeek → local extraction (`source_processing/extraction.py:116-142`); DeepSeek profile failure → regex fallback (`cv_profile_extraction.py:858`). The upload run sets `failed` status on unrecoverable errors (`cv_upload_jobs.py:35`).
- PDF rendering raises `RuntimeError` if the Node renderer script or Node itself is missing (`rendering.py:1351-1380`).
- Legacy Career Memory mutations return 410 (`career_memory.py` route), so no writes reach `backend/career_memory/service.py`.

## 7. Relevant tests and safe verification commands

Test files present at baseline:
- Career profiles, CV and baseline: `tests/test_career_profiles.py`, `tests/test_baseline_cv_replacement.py`, `tests/test_master_cv.py`, `tests/test_document_text.py`
- Evidence and memory: `tests/test_career_memory.py`, `tests/test_career_profile_evidence.py`, `tests/test_evidence.py`, `tests/test_evidence_library.py`, `tests/test_evidence_questions.py`, `tests/test_evidence_recommendation.py` (the only importer of `backend.career_memory.service`, L182, L239), `tests/test_evidence_review.py`, `tests/test_candidate_evidence.py`
- Experiences and suggestions: `tests/test_work_experience.py`, `tests/test_cv_bullet_suggestions.py`, `tests/test_source_text_review.py`, `tests/test_source_processing_pipeline.py`, `tests/test_source_processing_integration.py`
- Tailored documents: `tests/test_tailored_document_generation.py`, `tests/test_motivation_letters.py`, `tests/test_title_filter.py`
- Other: `tests/test_career_url_discovery_security.py`, `tests/test_cp042r.py` (imports the unregistered fixture routes directly, L172)

Safe verification commands (not executed in Phase 2):
```
python -m pytest tests/test_career_profiles.py tests/test_baseline_cv_replacement.py tests/test_master_cv.py tests/test_career_memory.py tests/test_career_profile_evidence.py tests/test_evidence.py tests/test_evidence_library.py tests/test_evidence_questions.py tests/test_evidence_recommendation.py tests/test_evidence_review.py tests/test_work_experience.py -q
python -m pytest tests/test_tailored_document_generation.py tests/test_motivation_letters.py tests/test_source_processing_pipeline.py tests/test_document_text.py -q
git grep -n "backend.career_memory" 58a96674 -- backend
```

## 8. Historical decisions and supporting commits

From `git log --oneline 58a96674 -- backend/career_memory backend/evidence backend/evidence_library backend/master_cv backend/profiles backend/work_experience backend/tools backend/scripts backend/application/baseline_cv_replacement_service.py backend/capabilities/tailored_documents backend/repositories/document_payloads.py`, selected:

| SHA | Subject |
|---|---|
| `af94ef4c` | feat: add branded social links to CVs (source of `cvSocialLinks.js` renderer input) |
| `6675338c` | feat: add editable workspace CV editor |
| `0bdbfb04`, `ef78e256` | Master CV payload fix / connect Master CV to backend |
| `b5a89474` | Move asset extraction to background worker (CV upload runs) |
| `20907b47` | Add PPTX text extraction |
| `4ebe8113` | deepseek fallback extraction pipeline career mem. |
| `2e56d028` | Complete Assisted Apply foundation through AA-221 |
| `f2114005`, `7a9c43ed`, `cf722066` | CP-044R/041R/040R evidence confirmation, question engine, auto-map |
| `41e9a616` | [CP-037R] evidence-backed motivation letters |
| `2fafb01c` | [CP-034R] reviewed baseline CV replacement |
| `b197a928` | [CP-033R] evidence question service |
| `78b2ff5c` | [CP-031R] Gemini source pipeline and AI provider badges |
| `863a6d81`, `6761718e`, `869002b1` | CP-014 evidence mapping, CP-015 evidence library, CP-020 motivation letters |
| `f04b284f` | [CP-029] replace misleading Career Memory actions |
| `57c9936e` | [CP-013] editable work-experience timeline |
| `f2958cc1` | [CP-007] Gemini Flash-Lite multimodal OCR and evidence extraction |
| `e5705c17`, `c3502ca0` | CV templates |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Career profiles CRUD, bind, rebind review, baseline CV replacement | VERIFIED (scope: static — 13 `career_profiles.*` routes registered, handlers call `rebind_service`/`baseline_cv_replacement_service`) |
| CV upload → background extraction | VERIFIED (scope: static — `documents.cv_upload` registered; run routed at `run_services.py:771`; provider calls not exercised) |
| Gemini/DeepSeek extraction quality and availability | IMPLEMENTED-UNVERIFIED (depends on keys; `GEMINI_API_KEY` not in render.yaml) |
| Workspace CV editor | VERIFIED (scope: static — editor branches in `documents.py:96,602,663` call `cv_editor.py`) |
| Master CV | VERIFIED (scope: static — 12 `master_cv.*` routes registered → `master_cv/service.py`, persisted in user metadata) |
| Canonical evidence journey, questions, library, work experiences, application bindings | VERIFIED (scope: static — routes registered in `__init__.py`, handlers import owned services; data in user/profile metadata) |
| CV bullet suggestions, evidence recommendations, source text review, career-profile evidence lifecycle | PARTIAL (routes registered, but state held in process-memory dicts, lost on restart and not shared across instances) |
| Tailored CV/cover-letter generation and PDF rendering in runs | IMPLEMENTED-UNVERIFIED (stages registered `stage_adapters.py:972`; needs DeepSeek and Node in the image; `Dockerfile.api/worker` copy renderer inputs) |
| Motivation letters | IMPLEMENTED-UNVERIFIED (route registered; DeepSeek-dependent) |
| Legacy Career Memory (`backend/career_memory/**`) | RETIRED/HISTORICAL (route is a read-only view plus 410; module imported only by `tests/test_evidence_recommendation.py`) |
| Career evidence Playwright fixture routes | RETIRED/HISTORICAL (not registered in `build_route_registry`; used only by `tests/test_cp042r.py`) |
| Career URL discovery tool | PARTIAL (CLI and tool present; API route disabled) |

### Deployment evidence (documentary only)

- No CV/career-specific production record was found. The handoff (`docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md`, Render `5dfdd106`) predates the baseline (U1).
- `render.yaml` api/worker build filters include the renderer inputs, and the Dockerfiles copy them. Whether the running image has Node available is UNKNOWN (WS-7).

## 10. Confirmed gaps and unresolved questions

| ID | Gap / question | Evidence |
|---|---|---|
| WS4-G7 | Four capability services keep state in module-level dicts (`_suggestions`, `_evidence_store`, `_reviews`, `_recommendations`). Suggestions, reviews and recommendations vanish on restart and diverge across api instances/worker. Persist, or retire? | §4 |
| WS4-G8 | `backend/career_memory/service.py` (487 lines) has no runtime importer; `backend/api/routes/career_evidence_fixture.py` is unregistered. Candidates for WS-11 residue review. | `git grep backend.career_memory`; `__init__.py` |
| WS4-G9 | Single-candidate residue in shared code: hard-coded fallback CV strings and default local CV paths (`profiles/cv_text.py:13-15`, `profiles/reusable_packages.py:6`). Do not copy the values; the owner should decide on removal. | code |
| WS4-G10 | `evidence.py` routes (`evidence.*`) use `backend/domain/evidence.py` while `career_evidence.*` and `evidence_items.*` use owned services. There are three parallel evidence models (profile evidence items, canonical candidate evidence, evidence library). Canonical source unclear. | §3 |
| U5 (label only) | `UNMERGED (feature/admin-analytics-final-production @ ce3718b0)` CV editor/perf commits are patch-equivalent to baseline `6675338c`, `5b900167`, `af94ef4c` (`git cherry` `-`). Nothing to restore. | primary §10 |
| U1 / U11 | Live revision unknown; full backend suite not run. | contradictions-and-unknowns |

## Agent context and remaining work

(a) **Context packet**
- Required reading: this doc, then the primary doc §2/§4/§11.
- Allowed paths: the §2 table.
- Tests: the §7 commands.
- Prohibited: live Gemini/DeepSeek calls in tests; changing `render.yaml`/Dockerfiles (WS-7); re-enabling `career-url-discovery` or Career Memory mutations; restoring unmerged branch content.

(b) **Registry**: covered by the single `app-services` row in the primary doc (§11 b). This slice is `app-services/career-documents` with test globs `tests/test_career_*.py`, `tests/test_evidence*.py`, `tests/test_master_cv.py`, `tests/test_tailored_document_generation.py`, `tests/test_work_experience.py`, `tests/test_baseline_cv_replacement.py`.

(c) **Gap/ticket candidates**: WS4-G7 (persist or retire in-memory stores), WS4-G8 (dead Career Memory module and fixture route), WS4-G9 (single-candidate fallbacks), WS4-G10 (evidence model consolidation).
