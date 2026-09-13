# Runr Assisted Apply — Permission Rationale

**Date:** 2026-07-18  
**Version:** 0.2.0  
**Extension ID:** `najcdfohhfgbjpbokhmmekkahghfhegp`  
**Target:** Chrome MV3

---

## Required permissions

| Permission | Purpose | Why it is required (not optional) |
|---|---|---|
| `activeTab` | Read the active employer-application tab URL and inject the application-form content script. | The extension cannot inspect or fill an application form without temporary access to the active tab. MV3 `activeTab` grants this only when the user clicks the extension action. |
| `identity` | Launch `chrome.identity.launchWebAuthFlow()` for the PKCE-based Runr session exchange. | The Chrome extension identity API is the only safe way to complete an OAuth-style connection without a custom redirect server or exposing secrets to the page. |
| `scripting` | Dynamically inject `application-form.js` and `controlled-field-bridge.js` into the active tab. | WXT/MV3 requires `scripting` for programmatic injection. The alternative (`content_scripts` in manifest) would run on every page load instead of only after a user action. |
| `sidePanel` | Open and manage the Runr Assisted Apply review side panel. | The extension provides all review, fill, and confirmation UI through Chrome's side panel API. |
| `storage` | Persist the session credential, tab state, and application package in `storage.session` (and the installation identifier in `storage.local`). | Without storage the extension cannot survive an MV3 service-worker restart or maintain per-tab application state. |

## Host permissions (mandatory)

| Pattern | Purpose |
|---|---|
| `https://runr-api.onrender.com/*` | The first-party Runr Assisted Apply API that serves application packages, accepts telemetry, and manages extension sessions. This is the only mandatory host permission. |

## Host permissions (optional — requested only after explicit user action)

| Pattern | Purpose | Why optional |
|---|---|---|
| `https://boards.greenhouse.io/*` | Read and fill supported application fields on Greenhouse-hosted job boards. | The extension can function (connect, review a bound package) without this permission. Portal access is requested only when the user clicks "Fill" or "Upload" on a detected Greenhouse tab. |
| `https://*.lever.co/*` | Read and fill supported application fields on Lever-hosted career pages. | Same rationale as Greenhouse. Lever access is requested only when the user takes an explicit action on a Lever tab. |

Both optional permissions are requested through the Chrome `permissions.request()` API, which shows a Chrome-native dialog. If the user denies, the extension continues to work — it simply cannot fill forms or upload documents on that portal. Users can also revoke these permissions at any time from `chrome://extensions` without disconnecting their Runr account.

## What the extension never does

- The extension never submits an application form (no DOM `submit()`/`requestSubmit()` call exists in any bundle).
- The extension never calls eval, `new Function()`, or dynamic imports from HTTP URLs.
- The extension never solves CAPTCHAs, signs declarations, accepts legal terms, or completes assessments.
- The extension never stores credentials, session tokens, document bytes, or permanent URLs outside the service-worker storage boundary.
- The extension never communicates with any host other than `runr-api.onrender.com` unless the user has explicitly granted portal-specific host permissions.

## Disclosures for Chrome Web Store

The following points are reflected in the store listing description and in the extension's post-install capability disclosure within the side panel:

1. **Review-first design:** Runr may fill supported fields with reviewed profile answers. The user reviews every change and submits the form themselves.
2. **No automatic submission:** The extension has no capability to submit an application. Every application is submitted by the user through the employer's own submit control.
3. **Account connection:** Connection is established through an explicit PKCE OAuth flow that creates a short-lived, revocable extension session. No web Clerk token is stored in extension storage.
4. **Optional portal access:** Site-specific access to Greenhouse and Lever job boards is always optional and requested only when needed for an active fill or upload operation.
5. **Privacy-safe telemetry:** Health telemetry contains only bounded adapter identifiers, lifecycle stages, and aggregate outcomes. No answers, document content, credentials, raw page markup, or personal identifiers leave the extension.
6. **Legal and demographic safeguards:** Legal answers always require explicit user confirmation. Demographic autofill is off by default and enabled only through an explicit preference.
7. **Data handling:** Application packages and document grants are temporary, versioned, and expire. Document bytes are downloaded to in-memory only and never written to extension storage or logs.

## Versioning

The extension follows semantic versioning. The initial store-ready version is **0.2.0** (V1 pilot).
