# Job CV customization implementation plan

Owner approved the design and explicitly requested uninterrupted implementation, commit, sync and deployment on 2026-10-11. Execute inline; no further design/plan approval gates.

Goal: complete the selected-job Customize CV flow with a working sample, real CV assessment, inline editing and export.

Spec: ../specs/2026-10-11-job-cv-customization-design.md

## Tasks

- [x] Add `frontend/src/lib/cvCustomization.js` and `.test.js`: normalize CVs and job requirements, assess five weighted dimensions, merge overlapping experience dates, transform only selected sections, draft persistence identities, escaped standalone HTML export. Start with failing tests for unsupported keywords, repeat-term scoring, section preservation, overlap and current-edit export.
- [x] Add anonymized `frontend/src/data/cvCustomizationSample.js`: complete source CV and curated supported enhancements for the recorded strategy-role scenario. Keep original private CV outside Git; no invented investment-banking/private-equity claims.
- [x] Add focused `components/cvCustomization/` components and CSS: modal drawer, five-row comparison, enhancement options, keyword evidence/confirmation, direct document editor, undo, section/entry controls, export and local draft recovery.
- [x] Integrate a compact right AI Tools rail and qualification chips in `JobsWorkspace.jsx`. Load actual CV assets through existing document endpoints; sample is opt-in. No pretend live generation or changes to saved-profile matching.
- [x] Add production-build browser tests covering sample completion, changed choices, direct edits, reopen, account/job isolation, exports, keyboard and mobile. Run unit/check/production-build suites and relevant Jobs/CV browser tests.
- [x] Final code review, fix material findings, document verification. Stage only feature files, commit and push current upstream. Build immutable frontend release on VPS using current production public settings, switch nginx root with rollback backup, verify public release and authenticated functionality where available.

## Constraints and review focus

Python commands use project `.venv` Python 3.12.7 only. No Archive exploration. No acquisition timers or database mutations. Preserve baseline CV and unrelated local changes. Use CV wording, real calculated scores, and explicit sample labeling. Verify stale source responses, storage errors, unknown requirements, unsupported confirmations, and export edits. Preserve existing backend Pro gates; current live generation is incomplete and must not be presented as available.

## Execution notes

- Baseline: `35a1d13e`, current checkpoint branch tracks origin; workspace contains unrelated report/doc changes. Work in place with exact file staging to preserve them. User explicitly removed repeated approval workflow.
- Brainstorming SKILL.md deleted from installed plugin cache at owner's request. Plugin reinstall/update may restore its packaged files.
- Deployment is frontend-only; current nginx serves an immutable customer release. Preserve backend services and acquisition pause.

Verification: 193 frontend tests, lint, production build/config check, and 8 desktop/mobile CV and External Jobs checks passed. Author review covered source preservation, scoring, persistence and exports. No independent reviewer was dispatched. Deployment verification is recorded in docs/reports/cv-customization-2026-10-11.md.
