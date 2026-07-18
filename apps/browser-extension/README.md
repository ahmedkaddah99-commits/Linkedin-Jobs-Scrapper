# Runr Assisted Apply browser extension

The current AA-01/AA-02 slices provide the guarded Chrome MV3 shell, review-only
side panel, Runr account connection and preference surface, Greenhouse fixture
inspection, one verified fixture fill, readback, and service-worker recovery.

Account connection uses an explicit-click `launchWebAuthFlow` authorization-code
and PKCE exchange. Pending authorization data and the short-lived extension session
are stored only in `storage.session`; content and page scripts cannot call Runr APIs
or receive the session token. The installation identifier is non-secret and stored
locally. Sensitive and demographic autofill preferences default off, while legal
answer confirmation cannot be disabled.

The local fixture button remains available only on a document explicitly marked as
a Runr test fixture. Real package-backed form filling arrives in later tickets.

Commands:

```powershell
npm install
npm run check
npm run test:e2e
```

Load `.output/chrome-mv3` as an unpacked extension after `npm run build` for a manual
Chrome smoke test. The extension has no adapter method or message capable of final
submission.

## Production connection identity

The Chrome Web Store listing must exist before the production connection flow can
be enabled. Copy its exact 32-character extension ID into the API deployment as:

```text
RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS=chrome-extension://<web-store-extension-id>
```

The value must be an exact origin: no wildcard, path, query, or trailing slash.
The derived callback is fixed in code as
`https://<web-store-extension-id>.chromiumapp.org/runr/connect`; the backend does
not accept a caller-supplied callback. Production environment validation fails
closed when the extension-origin allowlist is absent or malformed.
