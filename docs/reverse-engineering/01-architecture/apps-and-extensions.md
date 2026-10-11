> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Apps and extensions (`apps/**`)

Secondary WS-9 doc. It covers project structure, entrypoints, manifest, build, test configs and scripts. For behaviour, the never-submit boundary, the handshake, status and gaps, see the primary doc [assisted-apply.md](../05-subsystems/assisted-apply.md). Package exports are in [shared-packages.md](shared-packages.md). CI ownership is WS-7 ([ci-cd.md](../02-deployment/ci-cd.md)); the test map is WS-10 ([test-suite-map.md](../04-testing/test-suite-map.md)).

## 1. Purpose

`apps/` contains exactly one app, `apps/browser-extension`: npm package `@runr/browser-extension` v0.2.2, private, ESM, Node ≥22.13.0 (`apps/browser-extension/package.json`). It is the "Runr Assisted Apply" Chrome/Edge Manifest V3 extension built with WXT and React 19. It is a separate npm project (own `apps/browser-extension/package-lock.json`), not a root workspace, and is invoked from the root via `npm --prefix`.

## 2. Owned paths (77 files @58a96674)

| Area | Count | Files |
|---|---:|---|
| Root config | 8 | `apps/browser-extension/README.md`, `apps/browser-extension/package.json`, `apps/browser-extension/package-lock.json`, `apps/browser-extension/wxt.config.ts`, `apps/browser-extension/tsconfig.json`, `apps/browser-extension/vitest.config.ts`, `apps/browser-extension/playwright.config.ts`, `apps/browser-extension/playwright.edge.config.ts` |
| `entrypoints/` | 9 | `background.ts` (1376 lines), `application-form.ts` (253), `controlled-field-bridge.ts` (12), `linkedin-connections.ts` (22), `inactive-fixture-spike.ts` (80, testing), `sidepanel/App.tsx` (706), `sidepanel/main.tsx`, `sidepanel/index.html`, `sidepanel/style.css` |
| `src/` | 16 | `application-url.ts`; `auth/{browser-ports,config,connection-service,protocol,trusted-sender}.ts`; `documents/grant-validation.ts`; `fixture-runner.ts` (testing); `linkedin/connections.ts`; `permissions/host-permissions.ts`; `preparation/{external-command,local-session,report}.ts`; `review/panel-model.ts`; `state/tab-state.ts`; `success/possible-success-observer.ts` |
| `scripts/` | 3 | `apps/browser-extension/scripts/verify-manifest.mjs`, `apps/browser-extension/scripts/verify-assisted-apply-boundary.mjs`, `apps/browser-extension/scripts/generate-icons.mjs` |
| `public/icons/` | 4 | `runr-{16,32,48,128}.png` |
| `tests/` | 37 | 26 `tests/unit/*.test.ts`, 4 `tests/e2e/*.spec.ts`, `apps/browser-extension/tests/fixture-server.mjs`, 6 `tests/fixtures/*.html` (greenhouse, lever, reconciliation, same/cross-origin frame, runr-web-launch) |

`src/` module responsibilities:

| Module | Role |
|---|---|
| `auth/config.ts` | Production vs testing runtime config (API base, frontend origin, allowed web origins, Web Store URL) |
| `auth/connection-service.ts`, `auth/protocol.ts`, `auth/browser-ports.ts` | PKCE connection service, strict response parsers, browser/fetch/storage ports and `RunrAssistedApplyApi` |
| `auth/trusted-sender.ts` | Exact side panel / Runr web sender checks |
| `permissions/host-permissions.ts` | Optional portal host-permission helpers (narrow model) |
| `preparation/*` | External preparation command validation, local session record, progress report mapping |
| `review/panel-model.ts`, `state/tab-state.ts` | Side panel review model; per-tab `storage.session` state |
| `documents/grant-validation.ts` | Validate document-grant download metadata |
| `success/possible-success-observer.ts` | Detect possible post-user-submit success |
| `linkedin/connections.ts` | Extract LinkedIn connections and build CSV |
| `application-url.ts` | Comparable URL matching for bound application tabs |
| `fixture-runner.ts` | Testing-only fixture runner (guards `MODE !== "testing"`, L44) |

Governing docs: `apps/browser-extension/README.md` (matches code on the connection model and commands) and the documents listed in the primary doc §2.

## 3. Entrypoints and manifest

WXT discovers entrypoints from `entrypoints/`. `defineBackground` produces the MV3 service worker, `sidepanel/` produces `sidepanel.html`, and `defineUnlistedScript` files are built as standalone scripts injected at runtime with `scripting.executeScript` (no manifest `content_scripts`). Details: primary doc §3.1.

Manifest (`apps/browser-extension/wxt.config.ts`, function of `mode` and `browser`):

| Key | Value | Line |
|---|---|---|
| `manifestVersion` | 3; module `@wxt-dev/module-react` | 4-5 |
| `name` / `description` | "Runr Assisted Apply" / "…Runr never submits an application for you." | 7-9 |
| `version` | `0.2.2` (verifier asserts equal to package.json) | 10 |
| Chrome only | `key` (public key; derives extension id `najcdfohhfgbjpbokhmmekkahghfhegp`), `minimum_chrome_version: "116"` | 11-15 |
| Edge only | `minimum_edge_version: "120"`, no `key` | 16-18 |
| `icons`, `action` | 16/32/48/128 PNGs; title "Open Runr Assisted Apply" | 19-33 |
| `side_panel` | `sidepanel.html` | 34 |
| `permissions` | `activeTab`, `identity`, `scripting`, `sidePanel`, `storage` | 35 |
| `host_permissions` | production: Runr API + `www.linkedin.com` + `linkedin.com`; testing: `http://127.0.0.1/*` | 36-39 |
| `optional_host_permissions` | production: `boards.greenhouse.io`, `*.lever.co`; testing: `http://127.0.0.1/*` | 40-43 |
| `externally_connectable.matches` | production: `https://app.userunr.com/*`, `https://runr-frontend.onrender.com/*`; testing: `http://127.0.0.1/*` | 44-48 |

Host permissions follow the narrow model at baseline. The owner decision is broad-at-install, and that exists only UNMERGED; see primary doc §6.3 and WS9-G2.

## 4. Build, typecheck and test configuration

| File | Content |
|---|---|
| `apps/browser-extension/tsconfig.json` | Extends `.wxt/tsconfig.json` (generated by `wxt prepare`); `jsx: react-jsx`; `noUncheckedIndexedAccess`; `paths` map `@runr/ats-core`, `@runr/ats-core/*`, `@runr/extension-messages` to `../../packages/*/src` |
| `apps/browser-extension/vitest.config.ts` | Async config with `WxtVitest()` plugin (fake browser); Windows alias fix for `wxt/testing/fake-browser`; `environment: jsdom`; `include: tests/unit/**/*.test.ts`; `restoreMocks`; 30 s timeout |
| `apps/browser-extension/playwright.config.ts` | `testDir ./tests/e2e`, ignores `*.edge.spec.ts`, 60 s timeout, 1 worker, not parallel, html+line reporters, trace on failure; `webServer: node tests/fixture-server.mjs` on port 4174 |
| `apps/browser-extension/playwright.edge.config.ts` | Same, but `testMatch **/*.edge.spec.ts` and `channel: msedge` |
| Dependencies | `@runr/ats-core` and `@runr/extension-messages` via `file:../../packages/...`; `react`/`react-dom` ^19.2.7 |
| devDependencies | `wxt` ^0.20.27, `@wxt-dev/module-react`, `vitest` ^4.1.10, `jsdom`, `@playwright/test` ^1.60.0, `typescript` ^5.9.3, `@emnapi/runtime` (pinned for npm 10 CI, `dd4be9ab`) |
| `overrides` | `esbuild 0.28.1`, `shell-quote 1.10.0`, `tmp 0.2.7`, `uuid 11.1.1` |

Testing mode (`--mode testing`) switches the manifest to `127.0.0.1`, the runtime config to `http://127.0.0.1:4174` (`apps/browser-extension/src/auth/config.ts:15-20`), and enables fixture-only code paths.

Build outputs (not committed): `.output/chrome-mv3/`, `.output/edge-mv3/`. `verify-manifest.mjs` reads `.output/<browser>-mv3/manifest.json` (L6-7).

## 5. Scripts (`apps/browser-extension/package.json`)

| Script | Command | Notes |
|---|---|---|
| `dev` | `wxt` | dev server |
| `postinstall` | `wxt prepare` | generates `.wxt/` types |
| `typecheck` | `wxt prepare && tsc --noEmit` | enforces L1 `AtsAdapter` submit-name constraint |
| `test:unit` | `vitest run` | 26 unit files |
| `build` / `build:edge` | `wxt build` / `--browser edge` | production |
| `build:test` / `build:test:edge` | `--mode testing` | for e2e |
| `verify:manifest` / `verify:manifest:edge` | `node scripts/verify-manifest.mjs [edge]` | manifest shape, id, icons, permissions, host perms, no content_scripts, externally_connectable, source/bundle scans for eval/remote import/submit APIs/submit-like calls/fixture markers/secret markers |
| `verify:assisted-apply-boundary` | `node scripts/verify-assisted-apply-boundary.mjs` | ats-core regex boundary scan. **Not part of any `check*` script** (WS9-G1). |
| `generate:icons` | `node scripts/generate-icons.mjs` | icon PNGs |
| `package` | `wxt build && node scripts/verify-manifest.mjs` | |
| `test:e2e` / `test:e2e:edge` | `build:test[:edge]` then `playwright test [--config playwright.edge.config.ts]` | |
| `check` | typecheck → test:unit → build → verify:manifest | |
| `check:edge` | typecheck → build:edge → verify:manifest:edge | no unit tests |
| `check:all` / `check:all:edge` | `check[:edge]` + `test:e2e[:edge]` | |

Root wrappers (`package.json`, WS-7 owns): `check:extension` → `npm --prefix apps/browser-extension run check` (L9), `check:assisted-apply` → `check:all` (L10), `build:extension` → `build` (L16). Root `check` includes `check:extension` (L4).

CI (`.github/workflows/ci.yml`, WS-7): `assisted-apply-extension` (L111-141: Node 22, `npm ci --prefix apps/browser-extension`, `npx playwright install --with-deps chromium`, `check:all`, upload `playwright-report`/`test-results` on failure) and `assisted-apply-extension-edge` (L143-177: `msedge`, `check:edge`, `test:e2e:edge`). Both are required by `docker` (L178-185).

## 6. Invariants (build-level)
- There must be no manifest `content_scripts`, no `eval`/`new Function`/URL imports, no DOM `submit`/`requestSubmit` or submit-named calls in `entrypoints/`, `src/` or packages. Session/PKCE secret markers are allowed only in `background.js`, and there are no fixture markers in production bundles (`apps/browser-extension/scripts/verify-manifest.mjs:92-157`).
- Manifest version must equal the package.json version. The Chrome build must derive the reserved extension id. The Edge build must have no `key`.
- Full boundary invariants: primary doc §6.

## 7. Safe verification commands (not executed)
```bash
npm ci --prefix apps/browser-extension
npm --prefix apps/browser-extension run check
npm --prefix apps/browser-extension run verify:assisted-apply-boundary
npm --prefix apps/browser-extension run check:all
npm --prefix apps/browser-extension run check:edge && npm --prefix apps/browser-extension run test:e2e:edge
```

## 8. History
Created by `75bfdbc1` (2026-07-18). Edge target `7beea8ce`; store-ready permissions `42f6ba04`; CI gate repairs `ac798a5a`, `dd4be9ab`; LinkedIn sync entrypoint `92760a3a`; last change `fffef0dc` (2026-08-06). Full table in primary doc §8.

## 9. Status

| Capability | Classification |
|---|---|
| WXT project, entrypoints, MV3 manifest for Chrome/Edge | VERIFIED (scope: static — config and entrypoint files read; manifest keys cross-checked against `verify-manifest.mjs` assertions; not built) |
| Unit/e2e test configs, CI jobs wired | VERIFIED (scope: static — scripts in package.json and ci.yml L111-177 read; not run) |
| Boundary script in gates | PARTIAL (exists, not wired; WS9-G1) |
| Extension functionality end-to-end | IMPLEMENTED-UNVERIFIED (see primary §9) |
| Broad-host manifest, in-page assistant panel entrypoint | PLANNED-NOT-IMPLEMENTED on baseline: UNMERGED (feature/admin-analytics-final-production @ ce3718b0), T03 |

UNMERGED changes under `apps/` (36 A / 9 M across apps+packages, commit `0d7f2b5c`): new entrypoint UNMERGED `apps/browser-extension/entrypoints/assistant-panel.tsx`, `src/panel/*` (7 files), 8 unit + 1 e2e test, 12 ATS fixtures; modified `wxt.config.ts` (version 0.3.0, `https://*/*`, no optional hosts), `package.json`, `verify-manifest.mjs`, `background.ts`, `tests/fixture-server.mjs`. Review requirements are in primary doc §9.2.

### Deployment evidence (documentary only)
CI e2e PASS recorded in `docs/assisted-apply/ci/AA-225.md`. The Edge release report is `docs/reports/runr_assisted_apply_aa18_edge_report_2026-07-18.md`. Store publication state and installed version are UNKNOWN.

## 10. Gaps
WS9-G1 (boundary script not gated), WS9-G2 (host permission decision not on baseline), WS9-G5 (allocation names UNMERGED `assistant-panel.tsx`). Defined in the primary doc §10. Additional: WS9-G8, `check:edge` skips unit tests, which is acceptable because they are browser-agnostic but should be noted for WS-7.

## Agent context and remaining work
- **Context packet:** same as primary doc (a). Build/config work additionally requires reading `apps/browser-extension/wxt.config.ts`, `apps/browser-extension/scripts/verify-manifest.mjs` and `.github/workflows/ci.yml` (coordinate edits with WS-7).
- **Registry:** covered by the single `assisted-apply-extension` row in the primary doc (owned glob `apps/**`).
- **Ticket candidates:** wire boundary script into `check` and CI (WS9-G1); T03 manifest decision (WS9-G2).
