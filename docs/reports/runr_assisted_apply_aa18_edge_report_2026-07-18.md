# AA-18 — Stabilize and release the Edge target

**Status:** in_progress
**Date:** 2026-07-18
**Type:** HITL
**Blocked by:** AA-17 and an agreed Chrome stability window
**Visible plan coverage:** section 2 browser sequence

## Summary

The same guarded MV3 business logic that powers the Chrome extension is packaged
and verified for Microsoft Edge. Edge is Chromium-based and shares the same API
surface (chrome.* API namespace, Manifest V3, side panel, service workers).
WXT's --browser edge flag produces the Edge package from the identical
TypeScript source and shared packages (@runr/ats-core, @runr/extension-messages).

## Changes made

### 1. apps/browser-extension/wxt.config.ts
- Added browser parameter to the manifest callback.
- Chrome builds retain the existing key field (reserved store ID) and
  minimum_chrome_version: 116.
- Edge builds omit the key field (Edge assigns its own store ID) and set
  minimum_edge_version: 120.

### 2. apps/browser-extension/scripts/verify-manifest.mjs
- Accepts an optional targetBrowser CLI argument (defaults to chrome).
- For Chrome: verifies the public key derivation, reserved extension ID, and
  minimum_chrome_version.
- For Edge: asserts the key field is absent and minimum_edge_version is set.

### 3. apps/browser-extension/package.json
- Added scripts: build:edge, build:test:edge, verify:manifest:edge,
  test:e2e:edge, check:edge, check:all:edge.

### 4. apps/browser-extension/playwright.edge.config.ts
- New Playwright config targeting msedge channel.

### 5. apps/browser-extension/tests/e2e/assisted-apply.edge.spec.ts
- New E2E spec running the same fixture suite on Edge via chromium with
  channel: msedge. Tests cover fixture email, connection, Greenhouse package,
  Lever package, CV upload, tracker confirmation, and review panel.

### 6. .github/workflows/ci.yml
- New assisted-apply-extension-edge job installs msedge via Playwright,
  runs check:edge (typecheck + build + manifest verify), then runs
  test:e2e:edge. Added as a dependency of the docker build job.

## Edge-specific behavior

| Aspect | Chrome | Edge |
|---|---|---|
| Extension ID | Derived from public key | Assigned by Edge Add-ons store |
| key field in manifest | Required for ID stability | Omitted |
| Minimum browser version | minimum_chrome_version: 116 | minimum_edge_version: 120 |
| Extension URL scheme | chrome-extension://<id> | chrome-extension://<id> |
| API namespace | chrome.* | chrome.* |
| Service Worker | MV3 service worker | MV3 service worker |
| sidePanel API | Supported | Supported |
| scripting API | Supported | Supported |
| identity API | Supported | Supported |
| Permissions model | MV3, same set | MV3, same set |
| Build tool | WXT wxt build | WXT wxt build --browser edge |
| Output directory | .output/chrome-mv3/ | .output/edge-mv3/ |

## Excluded browsers and features (unchanged from Chrome V1)

The following remain explicitly out of launch scope for Edge V1:
- Firefox (requires Manifest V2 or Firefox-specific MV3 adaptation)
- Safari (requires Apple extension packaging)
- Mobile browsers (iOS/Android extension APIs differ)
- Workday (not a supported ATS portal)
- SuccessFactors (not a supported ATS portal)
- LinkedIn Easy Apply (not a supported ATS portal)
- Assessments (interactive/iframe assessments remain manual)
- CAPTCHA automation (never automated)
- Account creation (never automated)
- Arbitrary visual browser agents (no headless automation)
- Unsupported custom ATS forms (only Greenhouse and Lever are V1 targets)

## Manual verification checklist

### Connection and permissions
- [ ] Extension loads in Edge via edge://extensions with developer mode
- [ ] Side panel opens from the Edge toolbar action
- [ ] Connect to Runr launches launchWebAuthFlow through Edge identity API
- [ ] Connection callback completes on chromimapp.org redirect
- [ ] Disconnect revokes session locally and on backend

### Side panel and portals
- [ ] Side panel shows ATS detection (Greenhouse, Lever)
- [ ] Fixture email fill works on Greenhouse fixture
- [ ] Package-backed Greenhouse facts fill correctly
- [ ] Package-backed Lever facts fill correctly
- [ ] Mixed native controls work on both portals

### Uploads and tracking
- [ ] One-time document grant flow uploads CV to Greenhouse
- [ ] Cover letter upload works on accepted controls
- [ ] Supporting document upload is accepted/rejected by MIME type
- [ ] User-operated submit triggers possible-success observation
- [ ] Confirmation prompt creates Tracker record

### Scope boundaries
- [ ] CAPTCHA, signature, declaration, terms, assessment untouched
- [ ] Submit/requestSubmit never operated by extension
- [ ] Cross-origin frames remain manual
- [ ] Closed shadow roots remain manual
- [ ] Custom semantic controls remain manual

## Automated test results

The Edge fixture suite covers: AA-01 tracer bullet + worker recovery,
AA-02 explicit-click auth + session lifecycle, AA-04 Greenhouse package fill,
AA-05 Lever package fill, AA-11 CV upload, AA-14 tracker confirmation,
AA-09 review panel sections.

## Evidence

- WXT produces .output/edge-mv3/ and .output/edge-mv3-testing/ from same source.
- npm run check:edge exits 0 (typecheck + build + manifest verify).
- npm run test:e2e:edge passes all Edge scenarios using msedge channel.
- Edge production manifest has no key field and sets minimum_edge_version: 120.
- Edge testing manifest has same development host permissions as Chrome build.
- Edge extension URL scheme (chrome-extension://<id>) identical to Chrome.
- All storage.session, runtime.sendMessage, tabs.query, scripting APIs identical.

## Dependencies on AA-17

AA-18 is blocked until:
1. AA-17 Chrome V1 pilot and release gate is passed.
2. An agreed Chrome stability window (2-4 weeks post-Chrome-release) elapsed
   with no adapter-breaking regressions.
3. The source-plan remainder reconciliation is complete.

Once these gates are cleared, the Edge package can be submitted to the Microsoft
Edge Add-ons store using the same store listing content and privacy disclosures
approved during AA-17.
