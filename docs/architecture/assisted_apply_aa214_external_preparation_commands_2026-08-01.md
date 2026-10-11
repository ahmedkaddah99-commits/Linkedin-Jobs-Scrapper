# AA-214 external preparation command boundary

Status: implemented in the existing extension service worker and AA-213
preparation API boundary. No broad permissions or candidate payloads were
added.

## Trusted command validation

Repository-confirmed: `apps/browser-extension/entrypoints/background.ts`
continues to receive web messages through `browser.runtime.onMessageExternal`.
The AA-214 preparation branch first requires
`isExactRunrWebSender(sender, runtimeConfig.frontendOrigin)`, then
`isWebPreparationCommand` from
`apps/browser-extension/src/preparation/external-command.ts`. That function
uses AA-210’s strict version-1 `isAssistedApplyPreparationMessage` validator
and accepts only web `start`, `retry`, `review_activate`, and `cancel`.

`isFreshPreparationCommand` rejects messages older than the AA-210 freshness
window or more than 30 seconds in the future. `PreparationCommandReplayGuard`
and the worker replay map reject reused message IDs with changed fingerprints
and return the previous result for identical replays.

## Capability, ownership, and permission flow

Repository-confirmed: a start command requires a connected, unexpired
extension session, then retrieves the package through the existing bound
package endpoint. The backend therefore validates session ownership, package
binding, and package expiry/state. The worker verifies the package ID,
Greenhouse/Lever adapter capability, fill capability, and safe frozen package
application URL before any ATS tab creation.

The worker calls `hasPortalPermission` before `browser.tabs.create`. Missing,
denied, or revoked permission reports `permission_required` through the
sanitized AA-213 report route and creates no ATS tab. It never calls
`requestPortalPermission` from the external path. Optional permission requests
remain in the existing trusted sidepanel `REQUEST_PORTAL_PERMISSION` handler,
which is the direct extension user-gesture boundary.

After a sidepanel grant, a new explicit web retry can use the worker action
route, re-check permission, and resume/create the application tab inactive.
The worker does not require the sidepanel to remain open. Review/activate,
cancel, and retry commands are routed by the worker through the authenticated
extension preparation-action endpoint. Activation changes preparation review
state only; it does not submit an application.

## Data and safety boundary

External protocol messages contain only opaque Runr IDs, versioned capability
data, and bounded lifecycle fields. Browser tab/window IDs remain internal to
the worker and are not sent to web/backend APIs. Candidate values, DOM data,
selectors, document bytes/tokens, and submitted state are absent.

Tests:

- `apps/browser-extension/tests/unit/aa214-external-command.test.ts` covers
  trusted/untrusted origin, schema/version, stale/future commands, replay and
  sidepanel-closed worker validation.
- `apps/browser-extension/tests/unit/host-permissions.test.ts` covers missing,
  granted, denied, revoked, and already-granted permission behavior; the
  external path is intentionally read-only for permissions.
- `tests/test_aa213_preparation.py` covers package/session association,
  authorization, lifecycle, and extension action/report routes.
