# Job-specific CV customization

Implemented 11 October 2026 with owner approval to commit, sync and deploy.

## Delivered

Current Jobs and External Jobs details have an AI Tools rail. Customize CV opens baseline assessment, section/keyword choices, and a directly editable CV. A complete working sample uses the recorded strategy job with anonymized career evidence. Uploaded CVs load through the existing document editor API for assessment and manual draft editing. Live AI generation remains explicitly unavailable pending pipeline integration; the old queue action is no longer exposed as a finished-CV workflow.

Features: five weighted dimensions, hover/tap help, Quick/Full experience scope, evidence confirmation, before/after scores, section/entry/bullet controls, undo, local draft recovery, HTML download and Print/Save PDF. Baseline assets and saved-profile matching are unchanged. Confirmations do not count as document keyword coverage until included in the document.

Assessment is a lexical heuristic, not a proprietary Jobright score or hiring probability. Unknown requirements are excluded; repetition cannot inflate scores; overlapping dated roles count once. Specialized experience duration remains explicitly unverified. Drafts are scoped by account, originating job requirements, asset and revision, and saved on this device.

The private original-CV example is in ignored `tmp/cv-reference/`: extracted baseline, tailored HTML, two-page PDF and before/after assessment. No personal CV was committed. The default example scores 3.3 to 6.6; corporate strategy, investment banking and private equity require confirmation rather than being assumed from adjacent experience.

## Verification

- Twelve focused CV unit tests cover overlapping dates, aliases, unsupported keywords, section scope, removed-section scoring, normalization, custom sections, storage failures, draft identity and escaped exports.
- Full frontend check: 193 tests, lint and production build passed. Real-Jobs production configuration test passed.
- Eight desktop/mobile browser tests passed: sample generation, tooltip, edits, download content, reopen, undo, Escape-save/focus return, real CV assessment/manual editing, and External Jobs import/duplicate regression.
- Visually inspected desktop/mobile screenshots and both private sample PDF pages.
- Existing Career Evidence tests expect obsolete Add source evidence content while the route renders Career Profiles. Those unrelated failures remain. An older profile-match test also assumes a frontend working directory for its Python path; its root-directory run was not counted as matching verification. Matching implementation was not changed.
- Signed-in browser offered, but connector returned no available browser; Windows fallback initialization also failed. Authenticated live interaction is not claimed.

## Deployment and limits

The frontend-only deployment script builds an immutable release, preserves current public sign-in configuration, rejects test-auth bundles, detects concurrent nginx changes and restores the prior config on activation failure. No API/worker restarts, database writes or acquisition timer changes.

Live AI tailoring, backend draft synchronization, conversational rewriting and cover-letter generation remain future integrations. Uploaded-CV assessment uses the existing editor's normalized profile, including its existing extraction/profile fallbacks; extracted fields need review. Export uses HTML/browser PDF, not a new DOCX exporter.

Production deployed commit `1bf55aeddf6a4b769f85ebd0d0bb5be87013c78c` on 11 October 2026 (release generated 14:15 UTC). Public release metadata matches; `/jobs` and its `PersonalizedJobsPage-fab4ORnw.js` bundle return 200, and the bundle contains Customize CV and Generate sample CV. `/health/ready` reports ready; nginx, runr-api-candidate and runr-worker-candidate are active. The first activation rolled back because verification observed the previous nginx workers immediately after reload; the deployment script now retries convergence before declaring failure. The subsequent activation passed. Authenticated production interaction remains unverified because browser control was unavailable; desktop/mobile interaction was verified locally.
