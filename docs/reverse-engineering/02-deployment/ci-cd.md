> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# CI/CD

Secondary WS-7 doc. Release records and evidence classes are in [release-process-and-production-records.md](release-process-and-production-records.md). Image build details are in [docker.md](docker.md). The full test inventory and coverage classification belongs to WS-10: [../04-testing/test-suite-map.md](../04-testing/test-suite-map.md); this doc only describes what CI runs and how, not the tests themselves.

No workflow run was inspected on GitHub. Everything below is read from `.github/workflows/ci.yml` (219 lines) and root `package.json` at the baseline.

## 1. Purpose

`ci.yml` is the only workflow in `.github/**` (1 tracked file under `.github/`). It builds and tests on pull requests and on pushes to `main` or `deployment/render-turso-r2`. **It never deploys, migrates, or pushes an image.**

## 2. Triggers and concurrency

```yaml
on:
  pull_request:
  push:
    branches: [main, deployment/render-turso-r2]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```
(L3–15). `permissions: contents: read` is the only permission granted — no `packages: write`, no deploy tokens. A newer push to the same ref cancels an in-flight run.

## 3. Jobs

| Job | Runner | Depends on | What it runs |
|---|---|---|---|
| `backend` | `ubuntu-24.04` | — | ruff on `backend tests workspace_runner.py`; a curated pytest subset; a filtered `test_backend_api.py -k "assisted_apply or extension_cors or extension_origin or clerk_only_identity"` |
| `backend-full` | `ubuntu-24.04` | — | matrix `shard: [api, non-api]`; api runs `tests/test_backend_api.py`; non-api runs every top-level `tests/test_*.py` except that file; then ruff on `backend tests` |
| `frontend` | `ubuntu-24.04` | — | `npm ci --prefix frontend`; `npm --prefix frontend run test`; `npm --prefix frontend run check` (lint + build) |
| `assisted-apply-extension` | `ubuntu-24.04` | — | `npm ci --prefix apps/browser-extension`; Playwright Chromium install; `npm --prefix apps/browser-extension run check:all` |
| `assisted-apply-extension-edge` | `ubuntu-24.04` | — | same install pattern; Playwright msedge install; `npm run check:edge`; `npm run test:e2e:edge` |
| `docker` | `ubuntu-24.04` | `backend`, `frontend`, `assisted-apply-extension`, `assisted-apply-extension-edge` (L181–185) | builds `Dockerfile.api` and `Dockerfile.worker` with `push: false, load: false` |

`backend-full` is **not** in `docker`'s `needs:` list, so a `backend-full` failure does not block the `docker` job.

### Job detail: `backend` (L18–51)

1. `actions/setup-python@v5` pinned `python-version: "3.12"`, pip cache keyed on `requirements-linux.txt` (L24–29).
2. `pip install -r requirements-linux.txt "pytest>=9,<10" "ruff>=0.8,<1.0"` (L32) — the version pins here match `requirements-dev.txt` exactly.
3. `ruff check backend tests workspace_runner.py` (L35).
4. `pytest -q` a fixed list: `test_backend_application.py`, `test_sqlite_repositories.py`, `test_worker_service.py`, `test_phase0_contracts.py`, `test_job_dedupe.py`, `test_assisted_apply_connection_service.py`, `test_env_config.py` (L38–46) — this exact list, in this exact order, is duplicated verbatim in root `package.json`'s `check:backend` script (§5).
5. `pytest -q tests/test_backend_api.py -k "assisted_apply or extension_cors or extension_origin or clerk_only_identity"` (L48–51) — also duplicated in `package.json`.

### Job detail: `backend-full` (L53–88)

- `strategy.matrix.include`: `{shard: api, tests: tests/test_backend_api.py}` and `{shard: non-api, tests: tests}` (L58–63).
- The `non-api` shard shells out: `find tests -maxdepth 1 -name 'test_*.py' ! -name 'test_backend_api.py' -print | sort` into `mapfile`, then `pytest -q "${tests[@]}"` (L80–83) — this explicitly excludes only `test_backend_api.py`, not any other file, and does **not** descend into `tests/fixtures/` or nested test directories (`-maxdepth 1`).
- `fail-fast: false` (L57) — one shard failing does not cancel the other.
- No dependency caching for this job beyond pip (`cache-dependency-path: requirements-linux.txt`, same as `backend`).

### Job detail: `frontend` (L90–109)

- `actions/setup-node@v4` node 22, npm cache keyed on `frontend/package-lock.json` (L96–100).
- `npm ci --prefix frontend`, `npm --prefix frontend run test` (`node --test "src/**/*.test.js"`), `npm --prefix frontend run check` (`test && eslint src --max-warnings=0 && vite build`) — see `frontend/package.json:8,11`.
- **Frontend Playwright e2e (`npm run test:e2e`, `playwright test`) is not invoked anywhere in `ci.yml`.** Only the extension's e2e runs in CI. `frontend/e2e/` has 4 specs (one stale admin spec per C7/N-1), none CI-wired.

### Job detail: extension jobs (L111–176)

- Both jobs cache on `apps/browser-extension/package-lock.json` (a separate lockfile from the root/frontend ones).
- Chromium job: `npm run check:all` = `check && test:e2e` where `check` = `typecheck && test:unit && build && verify:manifest` (`apps/browser-extension/package.json:25,27`).
- Edge job: `check:edge` (`typecheck && build:edge && verify:manifest:edge`) then `test:e2e:edge` separately (L162–166), rather than a single `check:all:edge` script — even though `package.json:28` defines `check:all:edge` for exactly this combination, the workflow calls the two halves individually.
- Both upload `playwright-report`/`test-results` as artifacts on failure only (`if: failure()`, `if-no-files-found: ignore`).

### Job detail: `docker` (L178–219)

- `docker/setup-buildx-action@v3`, then two `docker/build-push-action@v6` steps, one per Dockerfile, each with `build-args: RUNR_RELEASE_COMMIT=${{ github.sha }}`, `RUNR_RELEASE_BRANCH=${{ github.ref_name }}`, `RUNR_RELEASE_SERVICE={api,worker}`, tagged `runr-{api,worker}:ci-${{ github.sha }}`, GHA cache scoped per image, `push: false`, `load: false`.
- Because `load: false`, the built image is not even loaded into the local Docker daemon for inspection — it is purely a build-succeeds check.

## 4. Root `package.json` scripts (WS-7-owned; audit N-2)

```json
"check": "npm run check:backend && npm run check:frontend && npm run check:extension",
"check:backend": "<ruff> && <pytest curated 7 files> && <pytest test_backend_api.py -k ...>",
"check:backend:api": "node scripts/run-python.cjs -m pytest -q tests/test_backend_api.py",
"check:backend:full": "node scripts/run-python.cjs -m pytest",
"check:frontend": "npm --prefix frontend run check",
"check:extension": "npm --prefix apps/browser-extension run check",
"check:assisted-apply": "npm --prefix apps/browser-extension run check:all",
"dev" / "dev:api" / "dev:worker" / "dev:ui": "concurrently ... node scripts/run-python.cjs ...",
"build": "npm --prefix frontend run build",
"build:extension": "npm --prefix apps/browser-extension run build",
"prod:build": "npm --prefix frontend run build",
"pm2:dev" / "pm2:stop" / "pm2:prod" / "pm2:logs" / "pm2:status": "pm2 ..."
```

- `check:backend` runs the identical ruff/pytest sequence as CI's `backend` job, but through `scripts/run-python.cjs`, which resolves `.venv/{Scripts,bin}/python{.exe,3}` and errors out if no venv exists (`run-python.cjs:5–23`) — a local-dev safeguard CI does not need since `setup-python@v5` provisions a system interpreter directly.
- `check:backend:full` runs the entire `pytest` suite with no filters — this is the closest local equivalent to CI's `backend-full` job, but as one shard, not two, and without ruff.
- `check` (the root aggregate) does **not** include `check:backend:full`, `check:backend:api`, or `check:assisted-apply` — those three are invoked individually, not through the aggregate. Whether CI calls `npm run check` at all: it does **not**; `ci.yml`'s `frontend` job calls `npm --prefix frontend run check` (the frontend-local script) directly, not the root aggregate.
- `pm2:*` scripts are the only repository reference to `ecosystem.config.cjs` besides the file itself (U9, documented in the VPS doc).

## 5. Dependency files CI reads

| File | Used by |
|---|---|
| `requirements-linux.txt` | `backend`, `backend-full` jobs (pip cache key and install); pinned versions `pytest>=9,<10`, `ruff>=0.8,<1.0` installed alongside it, matching `requirements-dev.txt` |
| `frontend/package-lock.json` | `frontend` job npm cache |
| `apps/browser-extension/package-lock.json` | both extension jobs npm cache |
| `requirements.txt` | **not referenced by CI** — it is the Windows-inclusive superset (adds `pywin32`) used locally, never installed in the Linux CI runners |
| `pyproject.toml` | not directly invoked by name in `ci.yml`, but `ruff` and `pytest` both read it implicitly (`[tool.ruff]`, `[tool.pytest.ini_options]`) when run from the repo root |

## 6. Invariants and failure handling

- **No deploy step anywhere in `ci.yml`.** No `render` CLI, no SSH/VPS step, no `git push` to a deploy branch, no Render API call. Deployment is entirely Render's own auto-deploy on a matching push (see the primary and render docs) plus manual VPS operator scripts (see the VPS doc) — neither is CI-driven.
- **No migration step.** `backend.database.migrate` is never invoked by any CI job.
- **`docker` job gates on 4 of 5 other jobs, not `backend-full`.** A broken `backend-full` shard can merge without blocking the Docker build check (WS7-G13, distinct numbering from the primary doc's rollback gap — kept local since it's CI-specific: renumbered here as **WS7-G16**).
- **Concurrency cancellation** means a force-push or rapid pushes to the same PR/branch can cancel an in-flight full-suite run before it completes; this is standard GitHub Actions behavior, not a bug, but means a green check on an earlier commit can be silently superseded without ever finishing on the latest one if pushes are frequent enough.
- **The `non-api` shard's `find -maxdepth 1`** means any test file the repository might add outside the top level of `tests/` (e.g., under `tests/fixtures/` if a `test_*.py` were ever placed there) would not run in `backend-full`, though this is a passive risk, not an observed defect — no such file exists at the baseline (`git ls-tree tests/` shows only `tests/fixtures/employer_coverage/connector_families.json`, not a test file).

## 7. Tests and safe verification commands

CI itself has no dedicated pytest coverage (a workflow YAML is not directly unit-tested), but its content is cross-checked by:
- `tests/test_rc022_build_release_contract.py::test_render_and_ci_select_distinct_api_and_worker_images` — asserts `Dockerfile.api` and `Dockerfile.worker` both appear in `ci.yml`.

Not executed in Phase 2:
```
git show 58a96674:.github/workflows/ci.yml | grep -n "^  [a-z-]*:$"      # list job names
git show 58a96674:.github/workflows/ci.yml | grep -n "needs:"             # docker job dependencies
git show 58a96674:package.json | grep -n '"check'
diff <(git show 58a96674:.github/workflows/ci.yml | sed -n '38,46p') <(git show 58a96674:package.json | grep -o 'test_[a-z_]*\.py' | sort -u)   # compare curated test lists (manual review, not an exact diff target)
.venv\Scripts\python.exe -m ruff check backend tests workspace_runner.py
node scripts/run-python.cjs -m pytest -q tests/test_backend_application.py tests/test_sqlite_repositories.py tests/test_worker_service.py tests/test_phase0_contracts.py tests/test_job_dedupe.py tests/test_assisted_apply_connection_service.py tests/test_env_config.py
```

## 8. History (`git log --oneline 58a96674 -- .github`, selected — note `.github` also contains non-workflow files owned elsewhere; this list is `ci.yml`-relevant)

| Commit | Subject |
|---|---|
| `c7bf7cbd` | deoployment prep initial setup |
| `cff506b4` | Run CI on Render deployment branch (added `deployment/render-turso-r2` to the push trigger) |
| `39d15b8f` | RC-022 separate release and runtime contracts (added the split `docker` job build steps for `Dockerfile.api`/`Dockerfile.worker`) |

`.github/**` is 1 tracked file per the owned-paths count in the primary doc §2 (only `ci.yml`; no `CODEOWNERS`, issue templates, or other workflows at the baseline).

## 9. Status

| Capability | Classification |
|---|---|
| PR and push-triggered CI on `main`/`deployment/render-turso-r2` | VERIFIED (scope: static — `ci.yml:3–8`) |
| Backend curated + full-suite pytest jobs | VERIFIED (scope: static — job bodies read in full) |
| Frontend unit test + lint + build gate | VERIFIED (scope: static — `frontend` job L90–109) |
| Frontend Playwright e2e gate in CI | VERIFIED absent (scope: static — no `playwright test` / `test:e2e` invocation anywhere in `ci.yml`'s `frontend` job or any other job). No doc or ticket plans to add one (WS7-G17). |
| Extension unit + e2e (Chromium and Edge) gate | VERIFIED (scope: static — both extension jobs) |
| Docker build-only verification (no push) | VERIFIED (scope: static — `push: false, load: false`) |
| CI as a deploy or migration trigger | VERIFIED absent (scope: static — no such step exists in the workflow) |
| CI runs actually passing at HEAD | UNKNOWN — no GitHub Actions run was inspected for this doc (no network access to GitHub used) |

### Deployment evidence (documentary only)

None. CI produces no deployment record consulted by this doc; the ledger, handoff and 2026-09-12 report all describe Render/VPS state, not GitHub Actions run outcomes. `RELEASE_LEDGER.md` entries like "focused release suite: 56 passed" (handoff L82) describe ad hoc local/agent test runs, not CI job results, and are documented in the primary doc, not here.

## 10. Gaps

| ID | Item |
|---|---|
| WS7-G16 | `docker` job does not depend on `backend-full`; a broken full-suite shard does not block the Docker build check |
| WS7-G17 | Frontend Playwright e2e (`frontend/e2e/**`, 4 specs) has no CI job; one spec targets retired admin routes (C7/N-1, WS-8 owns the spec itself) |
| WS7-G18 | Edge extension job calls `check:edge` + `test:e2e:edge` separately rather than the single `check:all:edge` script already defined in `apps/browser-extension/package.json:28` — cosmetic, not a functional gap, but a discrepancy between the workflow and the package script surface |
| — | `backend-full`'s `non-api` shard uses `-maxdepth 1`; would silently skip a future nested top-level test file (no current instance) |

## Agent context and remaining work

- **Read:** `.github/workflows/ci.yml`, root `package.json`, `pyproject.toml`, `requirements-linux.txt`/`requirements-dev.txt`.
- **Allowed:** `.github/**`, `package.json`, `package-lock.json`, `pyproject.toml`, `requirements*.txt`.
- **Tests:** `tests/test_rc022_build_release_contract.py::test_render_and_ci_select_distinct_api_and_worker_images`; any change to the curated test list in `ci.yml`'s `backend` job should be mirrored in `package.json`'s `check:backend` (and vice versa) since they are currently kept in exact sync by hand.
- **Prohibited:**
  - no adding a deploy, migrate, or credential-bearing step to `ci.yml`
  - no enabling `push: true`/`load: true` on the `docker` job without an owner decision
  - no removing `permissions: contents: read` without justification
- **Registry:** part of `deployment-release-ci` (primary doc).
- **Ticket candidates:**
  1. Add `backend-full` to the `docker` job's `needs:` list, or document why it is intentionally excluded (WS7-G16).
  2. Decide whether to wire frontend Playwright e2e into CI, retire the stale admin spec first (coordinate with WS-8), or explicitly record it as out of scope (WS7-G17).
  3. Align the Edge CI step with `check:all:edge` for consistency (WS7-G18), or document why the split is intentional (e.g., finer-grained failure attribution between build and e2e).
