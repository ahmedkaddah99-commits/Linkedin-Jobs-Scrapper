# Phase E job intelligence implementation report

## Product contract

- **Runr Summary** and **Structured Description** are generated projections of one immutable job-posting version.
- **Original Posting** is a separate employer-source projection and is never rewritten by summary generation.
- Missing employer facts remain `unknown`; generated code uses only facts present in the posting and never invents salary, experience, authorization, language, or qualifications.
- Free and Runr Pro receive both visible numeric match scores once precompute is available. A pending score is shown as pending, not as a confidence percentage.
- Free can open **Improve Resume** evidence review. Runr Pro-only rewriting queues a versioned tailored-resume generation cache entry; the worker produces an evidence-grounded generated payload.

## Scoring formulas

v1 (`phase_e_v1`) is deterministic ATS-style matching:

```text
score = round(100 * (0.60 * weighted_explicit_requirement_coverage
                     + 0.40 * exact_keyword_coverage))
```

v2 (`phase_e_v2`) is semantic/evidence-aware, with a deterministic final score:

```text
score = round(100 * (0.45 * weighted_requirement_coverage
                     + 0.25 * semantic_keyword_coverage
                     + 0.20 * verified_evidence_coverage
                     + 0.10 * preference_fit))
```

The payload reports matched keywords, missing keywords, matched requirements, unproven requirements, apparent non-matches, matched evidence, missing evidence, and a v1/v2 difference explanation. Neither score is an AI confidence percentage.

## Cache and model boundary

Cache identity is versioned by cache schema, canonical job ID, immutable job version ID, profile version, CV version, evidence version, evaluator/prompt version, intelligence kind, and a canonical input hash. A changed relevant input creates a new cache identity; old results are retained as immutable history.

GET `/personalized-jobs` and job/company detail paths only read cache rows. Missing intelligence is `pending` or `unknown`; those reads do not enqueue work or invoke a model. Worker/precompute code calls `enqueue_personalized_job_intelligence`, then `process_next_personalized_intelligence`; Pro rewriting uses the same worker queue with `phase_e_tailored_document_v1`. The optional Gemini provider is reachable only from the worker-side description generation path; deterministic grounded fallback remains available.

## Verification

- Backend cache/invalidation, deterministic fixture, read-path, Free/Pro entitlement, and evidence tests: `tests/test_phase_c_feed_performance_security.py`, `tests/test_phase_e_job_intelligence_async.py`, `tests/test_phase_e_personalized_jobs_intelligence.py`.
- Frontend selector/evidence/entitlement unit tests: `frontend/src/lib/personalizedJobIntelligence.test.js`.
- Playwright desktop/mobile accessibility and screenshot coverage: `frontend/e2e/phase-e-job-intelligence.spec.ts`.
- Captured screenshots: `frontend/screenshots/phase-e-job-intelligence-desktop-chromium.png` and `frontend/screenshots/phase-e-job-intelligence-mobile-chromium.png`.
- Final commit SHA: recorded after verification.
