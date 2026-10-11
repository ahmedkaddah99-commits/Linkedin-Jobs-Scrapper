# Assisted Apply AA-222 — explicit retry and recovery

Status: implemented on `deployment/render-turso-r2`.

## Lifecycle

Repository-confirmed: the extension keeps only transient tab ownership in
`chrome.storage.session` (`src/preparation/local-session.ts`). `tabs.onRemoved`
and `tabs.onUpdated` classify close, discard, and URL mismatch as explicit
interrupted outcomes. A missing local record after browser restart or extension
update returns `retry_required`; no startup listener opens an employer tab or
claims recovery.

Explicit retry revalidates the authenticated connection, fetches the package
again, checks the package association and ATS capability, checks the current
portal permission, and creates a new `active:false` tab. It does not reuse the
previous tab. The new run re-inspects and reruns the existing reconciliation/
fill path. Document upload requests continue through the existing backend grant
endpoint, which issues a new one-time grant per request and rejects expired or
consumed grants.

The bounded policy is three preparation attempts, represented by
`PREPARATION_MAX_ATTEMPTS` in the extension and backend domain. Backend retry
increments the durable attempt count and rejects retries at the limit. The
extension also fails closed before requesting a new tab when the limit is
reached.

## Safety outcomes

- Permission revoked: `permission_required` / explicit attention; no silent
  prompt or employer tab.
- Auth expired: `auth_lost`; explicit reconnect/retry required.
- Package unavailable or expired: the refetch fails closed; a new package is
  required rather than reusing cached content.
- CAPTCHA, MFA, login, unsupported controls, and ambiguous content remain
  manual/needs-attention boundaries.
- No retry path contains a terminal action or submission request.

## Evidence

- Local retry policy: `apps/browser-extension/src/preparation/local-session.ts`.
- Retry orchestration: `apps/browser-extension/entrypoints/background.ts`
  (`startPreparationCommand`, `handlePreparationCommand`).
- Backend bound: `backend/domain/assisted_apply_preparation.py` and
  `backend/application/assisted_apply_preparation_service.py`. Interrupted
  preparing sessions may be explicitly retried; active retry is never automatic.
- Grant freshness: `backend/application/assisted_apply_package_service.py`
  (`create_document_grant`) and existing AA-221 tests.
- Tests: `apps/browser-extension/tests/unit/aa222-retry-recovery.test.ts`,
  `apps/browser-extension/tests/unit/aa215-local-session.test.ts`, the AA-201
  inactive-tab suite, and the full Playwright fixture suite.

Unverified live-browser boundary: Chrome does not expose a reliable extension
event that can reconstruct a lost `storage.session` record after browser
restart/update. The implementation therefore reports retry-required on the
next explicit command and never auto-reopens a tab.
