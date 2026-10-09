# AA-203 Workday discovery record

Date: 2026-08-01  
Branch: `deployment/render-turso-r2`  
Prerequisite: AA-201 is present at commit `2bf5e4e`.

## Evidence boundary

**Repository-confirmed:** This repository contains no Workday browser-extension adapter, Workday application fixture, Workday-specific Playwright test, authorized Workday test account, or stored Workday session. The only Workday references are ATS discovery/routing data in `backend/connectors/ats_router.py` and `backend/connectors/company_career_discovery.py`; they do not provide application-form behavior.

**Not observed:** No live Workday page was opened. No credentials, candidate data, production host permission, login, CAPTCHA, MFA, anti-bot control, or application submission was accessed. Therefore all Workday-specific observations below are explicitly **unverified**.

## Locked executor baseline

**Repository-confirmed:** The locked declarative adapter contract is `AtsAdapter` in `packages/ats-core/src/index.ts`, with `detect`, `inspect`, `match`, `fill`, `authorizeReplacement`, `upload`, `validate`, and `detectPossibleSubmissionSuccess`. `ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN` statically prevents a submission method from entering the contract.

**Repository-confirmed:** `StandardFactsAdapter.inspect` classifies native inputs, textareas, selects, radios, checkboxes, dates, and files; discovers open shadow roots and same-origin frames; and records manual boundaries for closed shadow roots, cross-origin frames, and unsupported custom controls. `StandardFactsAdapter.fill`, `upload`, and `validate` are reusable executor operations, subject to those boundaries.

**Repository-confirmed:** `apps/browser-extension/src/success/possible-success-observer.ts` detects success banners, confirmation paths, and same-origin URL transitions only after a user-initiated terminal control. This is evidence detection, not submission.

**Repository-confirmed:** `apps/browser-extension/src/dynamic-form.ts` uses mutation, input/change, and file-change observation with a quiet-period snapshot. It is a reusable remount/dynamic-control primitive, but it does not prove Workday state preservation.

## Capability-gap matrix

| Capability | Existing reusable baseline | Workday evidence | Boundary / recommendation |
|---|---|---|---|
| Login and session | Extension connection is explicit and session state is handled by `ExtensionConnectionService` in `apps/browser-extension/src/auth/connection-service.ts`; ATS page access is separately permissioned. | **Unverified:** no authorized Workday session. | **Manual boundary:** never automate SSO, credentials, MFA, CAPTCHA, or anti-bot controls. Add a controlled login/session observation spike before any adapter work. |
| Employer/job page detection | Declarative `detect` is part of `AtsAdapter`; current URL detection is Greenhouse/Lever-specific in `packages/ats-core/src/index.ts`. | **Unverified:** Workday host/route variants and job/application transitions. | Reusable detector shape; Workday host and route rules are Workday-specific. |
| Native text fields | `inspect`/`match`/`fill` support semantic native controls. | **Unverified:** no Workday DOM evidence. | Reusable if controls are native and exposed; otherwise manual review. |
| Repeatable experience sections | No production repeatable-section engine exists. AA-202 only covers a pure sanitized reconciliation planner. | **Unverified:** add/remove controls, row identity, reorder behavior, and remount persistence. | **Workday-specific test:** inspect one controlled non-submitted experience section, add one row, remount, re-inspect, and verify stable visible identity. Do not build an adapter from assumptions. |
| Repeatable education sections | Same as experience; no production repeater executor. | **Unverified:** education row controls and persistence. | Separate Workday-specific spike; manual if row identity or controls cannot be proven. |
| Dates/date pickers | Native `input[type=date]` is classified and validated as `YYYY-MM-DD`. | **Unverified:** Workday date picker structure, locale, hidden inputs, keyboard behavior, and calendar overlays. | Native date path reusable; custom picker needs a Workday-specific declarative control or manual boundary. |
| Rich-text descriptions | Current field types cover text/textarea but do not establish a rich-text editor contract. | **Unverified:** contenteditable/editor iframe, serialization, toolbar, and readback. | Treat as manual until a non-submitted controlled editor spike proves set/readback safely. |
| Comboboxes | Native selects are supported; role-based custom controls are inspected but unsupported custom controls are manual. | **Unverified:** Workday ARIA combobox popup, async options, virtualization, and selection events. | Native select reusable; Workday combobox requires a dedicated declarative strategy and readback test. |
| Uploads | `AtsAdapter.upload` supports verified native file inputs and MIME/filename checks. | **Unverified:** Workday native input versus drop zone, size/type errors, async upload state, and replacement behavior. | Reuse native upload executor only after fixture evidence; otherwise manual. |
| Iframes | Same-origin frames are recursively inspected; cross-origin frames are explicit manual boundaries. | **Unverified:** Workday editor/upload/auth frame origins. | Existing boundary is reusable and conservative; no cross-origin permission expansion. |
| Shadow DOM | Open shadow roots are traversed; closed roots are manual. | **Unverified:** Workday custom element/shadow-root usage. | Reusable open-root traversal; closed roots remain manual. |
| SPA remounts | `dynamic-form.ts` observes mutations and waits for quiet; application runner can re-inspect after execution. | **Unverified:** Workday route transitions, component remount identity, and whether values survive rerender. | Reuse observer/re-inspection; add Workday remount test before trusting it. |
| Intermediate navigation | Generic URL transition observation exists only for success evidence and is armed by user terminal interaction. | **Unverified:** Workday step routes, partial-save behavior, and back/forward semantics. | Model as explicit Workday navigation states in discovery; do not infer submission or success from any route change. |
| Final-review detection | Success observer recognizes configured success selectors/paths after user action; adapter contract has no submit capability. | **Unverified:** Workday review/confirmation selectors and final transition. | Manual review remains required; add selector evidence only from a controlled non-submitted flow. |

## Manual boundaries

The following are explicit regardless of Workday findings:

- SSO, credentials, MFA, CAPTCHA, anti-bot challenges, and session recovery requiring user authentication.
- Any cross-origin iframe or inaccessible closed shadow root.
- Unknown custom controls, rich-text editors, custom date pickers, and unverified comboboxes.
- Any terminal submit button, final request, or success transition requiring an actual application submission.
- Any control whose readback cannot be verified after mutation or SPA remount.

## Reusable executor recommendation

**Recommendation — inferred from repository evidence:** The core executor is reusable for the proven subset: declarative detection/inspection, native semantic controls, native dates, verified native uploads, open shadow roots, same-origin frames, mutation quieting, validation, and review-only evidence. No repository evidence establishes a proven Workday blocker to that core.

**Unresolved:** Workday repeaters, rich text, custom comboboxes/date pickers, upload widgets, route/session boundaries, and final-review selectors remain unverified. They are not reasons to redesign the executor yet; each becomes a bounded discovery spike with a manual fallback if controlled evidence fails.

## Safe follow-up spikes

1. Use a sanitized or authorized non-submitted Workday page and record only DOM role/name/type, origin, route shape, and sanitized state transitions.
2. Observe login/session boundaries without entering or storing credentials; stop at SSO/MFA/CAPTCHA/anti-bot controls.
3. Test one experience and one education repeater with add, edit, remount, and readback; do not continue to review or submit.
4. Test one native/custom date, combobox, rich-text, and upload control independently.
5. Capture iframe/shadow-root boundaries and intermediate routes.
6. Identify review-state selectors without clicking a terminal submit control.

Every spike should produce sanitized traces and an explicit reusable/manual/unknown result. No personal or credential data belongs in the repository.

## Commands and result

- `git branch --show-current` — `deployment/render-turso-r2`.
- `git log --all --oneline --grep='AA-201' -i` — AA-201 present at `2bf5e4e`.
- `rg -n -i "workday|declarative adapter|centralized executor|executor|adapter" ...` — no Workday browser adapter, fixture, account, or session evidence found.
- No runtime tests were changed or required; this ticket is discovery-only.

AA-202 changes already present in the worktree were preserved. No commit was created for AA-203.
