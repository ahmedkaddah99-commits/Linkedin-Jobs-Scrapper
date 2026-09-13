# AA-223: Assisted Apply preparation UI baseline

Status: repository implementation record, 2026-08-01.

The extension sidepanel now reads a sanitized preparation projection from the
service worker. The projection contains only lifecycle status, ATS, and
aggregate filled/total counts plus a fixed technical reason. It does not cross
the panel message boundary with tab IDs, window IDs, candidate values,
document bytes, or document tokens.

## State coverage

Every local preparation state has a visible projection:

- `starting` and `waiting_ready` render as `queued`.
- `preparing` renders as `preparing`.
- `ready_for_review` renders as `ready_for_review` with an explicit review
  action.
- `review_activated` renders as a distinct review state stating that no
  submission occurred; it has no submit action.
- `permission_required` has an explicit portal-permission action.
- `closed`, `discarded`, and `navigation_mismatch` render as `interrupted`.
- `failed` renders as `needs_attention`.
- `auth_lost`, `expired`, and `retry_required` retain their distinct retry
  guidance.
- `cancelled` is terminal and explains that no application was submitted.

Reasons are sanitized and distinguish permission/auth/package problems,
technical interruption, and preparation attention. Counts are aggregate only;
unresolved is calculated as total minus filled.

## Action ownership and safety

Grant uses the existing explicit sidepanel permission request. Retry and cancel
route through the service worker and existing authenticated preparation action
contract. Retry reuses the AA-222 bounded retry path, which revalidates state
and creates a fresh inactive tab. Review uses the service worker's exact local
tab ownership and URL/discard checks before activating the tab. The sidepanel
does not need to remain open, and no submit control or submission message is
defined in the panel protocol.

## Evidence

`packages/extension-messages/src/index.ts` validates the four panel commands
and rejects unknown fields such as browser IDs or candidate payloads.
`apps/browser-extension/entrypoints/background.ts` projects local lifecycle
records and owns retry/cancel/activation. `apps/browser-extension/entrypoints/sidepanel/App.tsx`
renders the lifecycle states and explicit actions.

Unit coverage is in `apps/browser-extension/tests/unit/messages.test.ts`.
The extension Playwright coverage is the AA-223 test in
`apps/browser-extension/tests/e2e/assisted-apply.spec.ts`; it seeds a local
sanitized record, verifies permission and ready-for-review states, counts, and
the absence of submit controls.
