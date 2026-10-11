# Assisted Apply: frontend and application-flow comparison

Reviewed 2026-10-09. Scope: extension UI, design, navigation, and application completion. No backend changes. Competitor entries describe their public product documentation, not hands-on verification or an endorsement of coverage percentages.

## Sources

- [Simplify: using Copilot](https://help.simplify.jobs/help/articles/2415391-using-copilot-to-autofill-applications): panel sections, resume switching, cover letters, exact-question reuse, manual profile copying, and tracking.
- [Simplify Copilot](https://simplify.jobs/copilot): resume insights, question assistance, and tracking.
- [Jobright Autofill](https://jobright.ai/job-autofill): install, profile setup, autofill, review, and submission flow.
- [Jobright product walkthrough](https://jobright.ai/blog/supercharge-your-job-search-with-jobright-autofill/): tailored resumes, match scoring, and portal support requests. This article is dated 2025-08-22; it is older than the currently accessible landing page.
- [Runr provider evidence](simplify-parity-matrix.md): separate fixture evidence from actual live portal support.

## Matrix

| User task / design feature | Simplify | Jobright | Runr before | Implementation / remaining gap |
|---|---|---|---|---|
| Understand the next action | Open panel, select sections, autofill | Profile → application → autofill | Form button, profile fetched only during filling | Added readiness card, background profile loading, profile refresh, connect CTA, document shortcut. |
| Recover a failed account connection | Documented account setup | Documented account setup | Auto-connect attempt with no explicit retry control | Added explicit Connect / retry action with busy and error states. |
| Inspect profile before filling | Profile tab | Profile-powered autofill; detailed extension profile UI not established by these sources | Profile tab effectively empty until an autofill attempt | Profile is now fetched independently; autofill is not required to view it. |
| Copy details when autofill misses a field | Per-field profile copy, including work/education | Not established by primary sources reviewed | Bulk copy of seven contact/location fields; silent clipboard failures | Searchable contact, location, links, skills, experience, education; individual copy, success/failure feedback; selectable text. Bulk copy includes the same details. |
| Use profile on an unsupported page | Manual copy fallback | Not established | In-page panel intentionally absent; side panel had no usable profile browser | Added side-panel Profile workspace available independently of ATS recognition, using the same copy UI. |
| Edit profile and return to application | Profile editing | Account/profile setup | No visible edit action in in-page Profile tab | Added Edit profile; reload profile on returning focus or explicit refresh. |
| Resume keywords and match | Resume comparison, keyword gaps | Job match scoring | Existing profile-based keyword score | Retained score and keyword details; now available before autofill. Added pasted-job-description comparison when the form lacks posting text. Label now says Profile Match because it compares saved profile text, not an uploaded resume file. |
| Tailor resume from application | In-panel workflow / resume builder | Tailored resume integrated with autofill | Button sent an unhandled message | Added in-panel generation from confirmed profile facts and the job description, editable text preview, reviewed DOCX saving, and explicit attachment on the current application. CV Studio remains available for richer design editing. |
| See the documents for this application | Resume and cover-letter sections | Tailored resume used in autofill | Documents only in the separate package review panel | Added Documents tab with selected filenames, review/attach action, document management, tailoring action, and an explicit empty state. Metadata is shown only for the exact bound application URL. |
| Switch between multiple resume versions | Documented resume switching in panel | Tailored resume flow documented; exact picker behavior not established | Requires Runr's document workflow | Searchable native saved-document selector, exact-application selection persistence in the tab session, owned-document download, and explicit attachment/replacement. Local PDF/DOCX pickers remain available. |
| Generate a cover letter on the application | Documented paid generation in panel | Cover-letter tool linked on website; in-extension behavior not established | Existing external document tools | Added cover-letter drafting, editing, reviewed DOCX saving, and attachment to the detected cover-letter field. |
| Answer unique questions | Saved exact-question answers; AI assistance | Public autofill claims; specific unique-question UI not established | Existing package answers and correction/reuse flow hidden in side panel | Added question drafting from confirmed facts, editable preview, explicit reviewed-answer saving, and reusable answer copying alongside existing profile/package answers. Drafts do not autofill themselves. |
| Understand fill progress | Section-oriented application flow | One-click fill with review | Existing field progress and completion counts | Retained existing progress and review grouping; added Review actions that scroll/focus the current field, without activating form buttons. |
| Advance through application steps | Portal-dependent; no universal proof from sources | Portal-dependent; no universal proof | Guarded intermediate Continue already exists | Retained; shortened refusal copy to an actionable instruction. Provider-wide multi-step coverage remains outside this frontend change. |
| Track an application | Documented application tracking | Tracker documented | Existing confirmation flow in side panel only | Added visible Tracker action; simplified confirmation copy. Tracking still uses existing confirmed outcome flow. No new automatic tracking behavior claimed. |
| Customer-facing copy | Application task vocabulary | Application task vocabulary | CAPTCHA/declarations footer; internal execution and package terminology | Removed footer; replaced internal status prose with connect, fill, attach, review, and remaining-question instructions. Runtime behavior stays unchanged. |
| Narrow windows / visual consistency | Floating panel; exact responsive behavior not tested | Sidebar shown in marketing captures; responsive behavior not tested | Fixed 380px panel; collapsed tab referenced undefined color variables | Panel capped to viewport width, dynamic viewport height, compact tabs, readable copy rows, defined collapsed-tab colors. Side panel gains workspace navigation. |
| Request site support | Support documentation | Site requests documented | Report opened the review panel without a report form | Added Send report with durable account storage and a receipt, an admin-authenticated support inbox API, and clipboard fallback. No automatic email delivery is claimed. |

## Design and flow decisions

The primary application flow is now: open form → load profile → inspect documents/details → autofill → review unresolved fields → continue. Match, documents, answers, and profile copying are separate tabs with keyboard navigation; the existing review panel continues to handle approved answers, verified document attachment, and application confirmation. Runr web workspaces remain the editing destinations. Match scoring can use posting text pasted into the panel when the form has no description.

Loading a profile does not mutate the employer's form. Profile and package metadata travel through the service worker, and the new web navigation actions accept only fixed Runr destinations. Files are attached only after an explicit action using the provider-neutral helper. It preserves existing files by default, checks accepted formats, refuses ambiguous roles, and verifies filename readback. PDF/DOCX files are limited to 20 MB. The follow-up implements authenticated workspace routes for library access, generation, reviewed saving, and report delivery. Generation uses server-side confirmed profile facts and the existing DeepSeek configuration. No final-submission action or new live-provider coverage is introduced.

Technical safety explanations belong in developer documentation, rather than the application flow. Customer messages identify the current state and the next action. Only actual detected remaining questions prompt the user to complete something manually.

## Follow-up completion and release dependencies

The four implementation gaps from the first pass are implemented locally: saved-library selection, in-panel document generation and handoff, AI answer drafts with reviewed reuse, and a durable support-report destination. The document and answer workspaces also work in the extension side panel. Draft previews survive switching in-page tabs. Generated documents use a plain DOCX layout; richer template design stays in CV Studio. Reports are available through an admin-authenticated inbox endpoint, not an email integration or a new admin dashboard.

The new API module and worker were deployed to production at `8e9d5d73` on 2026-10-09 and verified live. Extension 0.3.1 is rebuilt for testing. The implementation reuses the existing DeepSeek key, account metadata, and document object storage; no database migration is introduced. See [workspace API and release notes](workspace-api-2026-10-09.md) for deployment IDs, the corrected release pin, and live smoke-check evidence.

Live browser coverage for upload and multiple steps across additional providers remains unverified. Local fixture acceptance does not establish universal live ATS coverage.

## Verification

Verification commands: extension typecheck, unit tests, production manifest/boundary checks, and Chromium fixture acceptance. The additional acceptance scenario verifies profile availability before filling, form non-mutation, clipboard copying, unsupported-page side-panel access, local document selection/attachment/preservation/replacement, document management navigation, and the repaired tailoring action. Fixture screenshots are generated at `apps/browser-extension/test-results/assisted-apply-profile.png` and `assisted-apply-documents.png` when that scenario passes.

Executed results on 2026-10-09:

- Final TypeScript check passed.
- Production packaging, manifest verification, and Assisted Apply boundary verification passed; Chrome build is `.output/chrome-mv3`, version 0.3.0.
- Targeted unit checks passed across runs, covering profile formatting, clipboard feedback, document controls, sender/message handling, panel models, provider behavior, and inspector isolation. The full unit suite was not completed; initial concurrent worker startup failures required targeted reruns.
- All nine automatic-panel Chromium fixture scenarios passed. The existing side-panel AA-09 review scenario also passed.
- After the final copy/loading-state changes, the new comprehensive frontend browser scenario passed again (15.3 seconds). An invalid test-hook timeout argument discovered during final checking was corrected before this run.
- Scoped `git diff --check` passed.

Browser validation also caught the inspector traversing Runr's own shadow-root document picker and treating it as an employer upload field. The inspector now excludes the Runr panel while retaining traversal of employer shadow roots; a regression test covers this distinction. These results cover local fixtures, not live production portal coverage.

Follow-up verification: 11 backend workspace/package checks passed, including a real storage/DOCX round trip and cross-account denial; six frontend unit checks passed; TypeScript and production package/manifest/boundary checks passed for 0.3.1. Eight unchanged Chromium scenarios passed in the regression run; the expanded ninth scenario passed on its corrected rerun (23.3 seconds), covering both resume and cover-letter generation/editing/saving/attachment, draft preservation across tabs, reviewed-answer reuse, and a report receipt. Generation calls are mocked in tests; no live model request or live application submission was made.

The required API/CLI regression suite also completed: 129 tests and 19 subtests passed, with five dependency deprecation warnings.
