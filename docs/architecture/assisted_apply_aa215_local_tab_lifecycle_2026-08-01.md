# Assisted Apply AA-215 — local tab lifecycle

Status: implemented spike on `deployment/render-turso-r2`; no production ATS submission behavior is added.

## Decisions and evidence

| Conclusion | Classification | Evidence |
|---|---|---|
| Preparation ownership is local to the extension and stored in `chrome.storage.session`. | Repository-confirmed | `apps/browser-extension/src/preparation/local-session.ts`: `PREPARATION_LOCAL_RECORD_KEY`, `readPreparationLocalRecord`, `writePreparationLocalRecord`; existing `apps/browser-extension/src/state/tab-state.ts`: `browser.storage.session`. |
| A preparation record contains the local `tabId`/`windowId`, package identity/version, frozen application URL, bounded local status, attempt, and aggregate counts. | Repository-confirmed | `local-session.ts`: `PreparationLocalRecord`; no record is sent through `packages/extension-messages` or backend request bodies. |
| Browser IDs do not cross the web/backend boundary. | Repository-confirmed | `apps/browser-extension/entrypoints/background.ts`: `reportPreparationFromExtension`, `reportPreparationProgress`, `applyPreparationExtensionAction`; their bodies contain preparation/package IDs and bounded result fields only. |
| The start path rejects a second active preparation. | Proposed/implemented | `background.ts`: `startPreparationCommand`; `local-session.ts`: `hasActivePreparation`. The bounded choice is rejection (`status: "busy"`), not queueing. |
| ATS tabs are created inactive and are never silently recreated. | Repository-confirmed | `background.ts`: `browser.tabs.create({ url: applicationUrl, active: false })`; review and retry require the local record and exact owned tab. |
| Readiness is event-driven. | Repository-confirmed | `background.ts`: `waitForPreparationTabReady` listens to `tabs.onUpdated`; `application-form.ts` sends `ASSISTED_APPLY_CONTENT_READY`; the handshake has a bounded timeout and no polling/sleep. |
| The immutable package is dispatched only after the exact tab is ready. | Repository-confirmed | `background.ts`: `writeTabPackage`, `runGreenhousePackageOnTab`, `runLeverPackageOnTab`; package validation remains `isApplicationPackagePayload`. |
| Backend progress is sanitized aggregate progress. | Repository-confirmed | `background.ts`: `reportPreparationProgress`; only `completed`, `total`, bounded `status`, and preparation-scoped review ID are sent. |
| Review activation can activate only the exact local session-owned tab whose URL still matches the frozen URL and whose local state is `ready_for_review`. | Repository-confirmed | `local-session.ts`: `canActivateExactPreparationTab`; `background.ts`: `review_activate` branch calls `tabs.get`, `tabs.update(record.tabId, { active: true })`, and then the authenticated backend action. |
| Close, discard, navigation mismatch, cancellation, and local state loss have explicit outcomes. | Repository-confirmed | `background.ts`: `tabs.onRemoved`, `tabs.onUpdated`, cancel branch; `local-session.ts`: `classifyPreparationTabChange`; missing storage record returns `retry_required` for review. |
| Browser restart/update recovery is not automatic. | Repository-confirmed | The local record is session-scoped; no persistent browser ID or silent tab recreation exists. An absent record cannot pass `canActivateExactPreparationTab`. |

## State transitions

`start` first checks the session record. If an active record exists, the new request is rejected as `busy`. Otherwise, after authenticated package retrieval and permission verification, the extension creates or reuses a matching URL tab inactive and writes `waiting_ready`. `tabs.onUpdated` reaches a complete matching URL, then the content script sends the local ready handshake. The worker dispatches the package, reports aggregate `progress`, and reports `ready_for_review`.

`review_activate` requires the stored record, exact tab ID, matching URL, non-discarded tab, and `ready_for_review`. It activates that tab only, then reports the authenticated backend action. A missing/closed/mismatched tab returns `retry_required` and does not create another tab.

`cancel` writes `cancelled` before reporting the backend action. `tabs.onRemoved` writes `closed`; a discarded tab writes `discarded`; a different URL writes `navigation_mismatch`. Permission denial is `permission_required`, and expired/missing connection handling is `auth_lost`. State loss after browser restart/update is represented by the absence of a local record and requires explicit retry/start handling.

## Safety boundary

The existing ATS runners remain bounded to field filling and evidence observation. AA-215 does not add submit clicks, `requestSubmit`, `form.submit`, Enter submission, terminal requests, success transitions, or final navigation. Existing final-confirmation protections remain in `apps/browser-extension/entrypoints/background.ts` and `apps/browser-extension/src/success/possible-success-observer.ts`.

## Tests and limitations

`apps/browser-extension/tests/unit/aa215-local-session.test.ts` covers storage reconstruction, state loss, discard/navigation classification, exact-tab activation, and wrong-tab protection. Existing unit coverage continues to cover AA-214 origin, schema, freshness, replay, permission, binding, and sidepanel-closed boundaries.

The controlled Playwright browser path was not run in this ticket because it requires the local fixture server and extension build; the existing AA-201 fixture spike remains test-only. Live Chrome restart/update and real ATS authentication were not exercised. These are explicit follow-up evidence gaps, not inferred successes.
