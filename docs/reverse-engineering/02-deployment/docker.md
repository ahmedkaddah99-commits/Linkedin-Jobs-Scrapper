> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Docker images

Secondary WS-7 doc. Release records and evidence classes are in [release-process-and-production-records.md](release-process-and-production-records.md). Render's use of these images is in [render.md](render.md); CI's build-only use is in [ci-cd.md](ci-cd.md).

No image was built or run for this doc. Everything below is read from the three Dockerfiles at `58a96674`.

## 1. Purpose

Three Dockerfiles exist. Only two are wired into Render or CI.

| File | Lines | Referenced by |
|---|---|---|
| `Dockerfile.api` | 71 | `render.yaml:50` (`runr-api`), `.github/workflows/ci.yml:195` (build only) |
| `Dockerfile.worker` | 69 | `render.yaml:166` (`runr-worker`), `.github/workflows/ci.yml:210` (build only) |
| `Dockerfile` (root) | 47 | **Unreferenced.** `git grep -n "dockerfilePath\|file: Dockerfile\b"` finds no match outside `.api`/`.worker`. `docs/RC022_BUILD_RELEASE_STAGING.md:50` states it is kept "only as a compatibility image for existing local consumers". |

## 2. Root `Dockerfile` (unreferenced)

- Multi-stage: copies a Node 22 runtime from `node:22-bookworm-slim`, then builds on `python:3.12-slim-bookworm` (L1–3).
- Installs `ca-certificates`, `fonts-dejavu-core`, `fonts-liberation`, `libreoffice-writer`, `tesseract-ocr`, `tesseract-ocr-deu` (L10–17).
- Creates `/app/.venv` and installs `requirements-linux.txt` (L19–22).
- Installs frontend deps and Playwright Chromium (L24–29), then `COPY . .` (L31, the whole repository, unlike the split images).
- Creates non-root user `runr` (uid 10001), `USER runr` (L35–38).
- `CMD ["./deploy/start.sh", "api"]` (L42).
- It does **not** build the static frontend (`npm run build` is absent) and does **not** copy `scripts/` explicitly (it gets everything via `COPY . .`).
- `test_rc022_build_release_contract.py::test_runtime_dockerfiles_are_separate_and_do_not_build_static_frontend` asserts `"npm --prefix frontend run build" not in legacy` — true, since this Dockerfile never runs the frontend build at all (there is no `npm run build` step for any target here).

## 3. `Dockerfile.api`

- Same base stages (L1–3) and `ARG`s `RUNR_RELEASE_COMMIT`, `RUNR_RELEASE_BRANCH`, `RUNR_RELEASE_SERVICE=api` (L4–6), all defaulting to `unknown`/`api`.
- OCI labels embed those args plus `org.runr.release.contract="runr-contract-v1"` (L8–13).
- `ENV RUNR_IMAGE_SERVICE=api` plus the same args re-exposed as env (L15–21).
- Same OS packages as the root image (L28–35), with a comment (L26–28) explaining the API still needs LibreOffice/Tesseract for "synchronous CV/document compatibility routes and the server-side HTML CV renderer".
- Creates `/app/.venv`, installs `requirements-linux.txt` (L37–40).
- Copies **only** `frontend/package.json` + `package-lock.json`, runs `npm ci` and `npx playwright install --with-deps chromium` in `frontend/` (L42–48) — Playwright is installed even though the API does not scrape; it needs Chromium for the server-side CV PDF renderer.
- Copies `backend/`, the three CV-runtime frontend files (`render-cv-pdf.mjs`, `cvStudio.js`, `cvSocialLinks.js`), `workspace_runner.py`, `deploy/start.sh` (L50–55) — **not** the rest of `frontend/` and **not** `scripts/`.
- `chmod +x deploy/start.sh`, creates user `runr` uid 10001, `mkdir -p /app/.backend_data /ms-playwright`, chowns (L57–60).
- `USER runr`, `EXPOSE 8000`, `CMD ["./deploy/start.sh", "api"]` (L62–66).

## 4. `Dockerfile.worker`

- Same base, args and labels pattern with `RUNR_RELEASE_SERVICE=worker` (L1–13).
- Comment (L20–22): workers execute "CV extraction, document conversion, rendered career-source fallbacks, and server-side PDF generation".
- Same OS packages (L23–30).
- Creates `/app/.venv`, installs `requirements-linux.txt` (L32–35), then **an extra explicit** `playwright install --with-deps chromium` at the venv level (L36) before the frontend-scoped Playwright install that both Dockerfiles share (L38–42) — the worker installs Chromium twice (venv-level and again inside `frontend/`'s own `npx playwright install`).
- Copies `backend/`, the three CV-runtime frontend files, **plus `scripts/`** (unlike the API image), `workspace_runner.py`, `deploy/start.sh` (L44–50).
- Same user/permission setup (L52–55).
- `USER runr`, **no `EXPOSE`** (background worker, no inbound port), `CMD ["./deploy/start.sh", "worker"]` (L57–59).

## 5. Differences at a glance

| | root `Dockerfile` | `Dockerfile.api` | `Dockerfile.worker` |
|---|---|---|---|
| Referenced by Render/CI | no | yes | yes |
| `COPY` scope | whole repo | `backend/`, 3 frontend files, `workspace_runner.py`, `deploy/start.sh` | same + `scripts/` |
| `EXPOSE` | none stated | 8000 | none |
| Playwright installs | 1 (frontend-scoped) | 1 (frontend-scoped) | 2 (venv-scoped + frontend-scoped) |
| OCI release labels | none | yes | yes |
| Frontend build (`npm run build`) | never | never | never |
| Static frontend files (`frontend/dist`) | never copied | never copied | never copied |

None of the three images serves the built static SPA; that is `runr-frontend`'s job on Render (`staticPublishPath: ./dist`, built outside Docker) or `backend/static_server.py` on the VPS/PM2.

## 6. `.dockerignore` (56 lines)

Excludes, among others: `.git`, `.github`, `.codex`, `.venv`, `__pycache__`, `*.sqlite*`, `.env*`, `node_modules`, `frontend/node_modules`, `frontend/dist`, `docs/*` (except `docs/legal/`), `tests`, `.backend_data`, `generated_docs`, `Jobs-Urls`, `Archive`, `test CV`, `test-CV`, `backups`, `user_config/candidate_assets`, `user_config/profile_photos`, caches, and `*.zip`/`*.tar*`.

Consequence: `tests/` and most of `docs/` never reach the Docker build context, keeping images smaller and avoiding leaking evidence-package artifacts; this applies to all three Dockerfiles since `.dockerignore` is not per-file.

## 7. Flows

```
Render api/worker build:
  render.yaml dockerfilePath ./Dockerfile.{api,worker}
    → docker build . -f Dockerfile.{api,worker}  (no build-args passed by render.yaml)
    → ARG RUNR_RELEASE_COMMIT/BRANCH default "unknown"
    → ENV bakes those defaults; deploy/start.sh's release_contract falls back to
      RENDER_GIT_COMMIT / RENDER_GIT_BRANCH at container start (see release-process doc §4)

CI build (.github/workflows/ci.yml "docker" job):
  docker/build-push-action@v6, context "." , file Dockerfile.{api,worker}
    build-args: RUNR_RELEASE_COMMIT=${{ github.sha }}, RUNR_RELEASE_BRANCH=${{ github.ref_name }},
                RUNR_RELEASE_SERVICE={api,worker}
    push: false, load: false   → image is built, verified buildable, then discarded
```

## 8. Invariants and failure handling

- Both runtime images require `/app/.venv` to exist because `deploy/start.sh:15–19` exits 1 without it, and both Dockerfiles create it (§3, §4). The 2026-09-12 report (DOC-UNTRACKED, L165–166) records this as a historical Render pre-deploy root cause before the split images existed.
- Both images run as non-root `runr` (uid 10001); `test_runtime_dockerfiles_are_separate_and_do_not_build_static_frontend` asserts `"USER runr" in dockerfile` for both.
- Neither runtime image runs `npm run build`; the same test asserts `"npm run build" not in dockerfile` for both.
- The worker's double Playwright install is redundant but not contradictory: the venv-level install (`Dockerfile.worker:36`) targets `/app/.venv`'s Playwright, while the `frontend/`-scoped install (shared with the API image) targets whatever Playwright the frontend's own `npm ci` pulls in. No code confirms these are the same browser cache path beyond the shared `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` env (WS7-G12).
- CI's `docker` job builds both images with `github.sha`/`github.ref_name` as release labels but never runs a container from them, so the images are structurally validated only (they build) — no smoke test of `deploy/start.sh` inside the container is present in CI.

## 9. Tests and safe verification commands

- `tests/test_rc022_build_release_contract.py::test_runtime_dockerfiles_are_separate_and_do_not_build_static_frontend` (asserts `USER runr`, no `npm run build`, Playwright Chromium install, `tesseract-ocr`, `libreoffice-writer`, `RUNR_IMAGE_SERVICE=api`/`worker`).
- `tests/test_rc022_build_release_contract.py::test_render_and_ci_select_distinct_api_and_worker_images`.

Not executed in Phase 2:
```
git show 58a96674:Dockerfile | grep -n "COPY \. \."
git show 58a96674:Dockerfile.api | grep -n "COPY \|EXPOSE\|CMD"
git show 58a96674:Dockerfile.worker | grep -n "COPY \|playwright install\|CMD"
docker build -f Dockerfile.api -t runr-api:local .     # not run in Phase 2
docker build -f Dockerfile.worker -t runr-worker:local .
.venv\Scripts\python.exe -m pytest -q tests/test_rc022_build_release_contract.py
```

## 10. History (`git log --oneline 58a96674 -- Dockerfile Dockerfile.api Dockerfile.worker`)

| Commit | Subject |
|---|---|
| `c7bf7cbd` | deoployment prep initial setup (root Dockerfile, first version) |
| `aae3028f` | Linux Production Setup + Clerk's JWT |
| `39d15b8f` | RC-022 separate release and runtime contracts — introduced `Dockerfile.api`/`Dockerfile.worker` as a split from the single root image, added OCI release labels and the `/app/.venv` contract |
| `15f58623` | fix(acquisition): install Python browser runtime and preserve partial outcomes — Playwright/venv fixes reaching the split images |

The root `Dockerfile` has not changed since before the split (`39d15b8f` did not touch it per the earlier `git diff --shortstat` at 848408f3, confirmed unchanged in the unchanged-directories list of the phase-1 delta audit).

## 11. Status

| Capability | Classification |
|---|---|
| Split API/worker images with OCI release labels | VERIFIED (scope: static — both Dockerfiles read in full; labels at L8–13) |
| Root Dockerfile unreferenced by Render or CI | VERIFIED (scope: static — `git grep` for `dockerfilePath`/`file:` across `render.yaml` and `.github/workflows/ci.yml` finds only `.api`/`.worker`) |
| Non-root runtime user in both images | VERIFIED (scope: static — `USER runr` present in both) |
| `/app/.venv` present at image build time | VERIFIED (scope: static — `python -m venv /app/.venv` in both) |
| CI builds both images on every push/PR | VERIFIED (scope: static — `ci.yml` `docker` job, see ci-cd.md) |
| Images pushed to any registry from this repo's CI | VERIFIED (scope: static — `push: false, load: false` in `ci.yml`, both build steps) — CI never pushes. Whether Render's own pipeline pushes/pulls internally is UNKNOWN (outside this repo). |
| Worker's double Playwright install intentional vs redundant | UNKNOWN (WS7-G12) |

### Deployment evidence (documentary only)

- The 2026-09-12 report (DOC-UNTRACKED, L43–44) records "The Docker images now create and use `/app/.venv`, matching the launcher contract" as a fix applied before that report's date — consistent with `39d15b8f`/`15f58623` already being in the baseline history.
- No record states which image digest Render actually deployed; Render's own build-from-source pipeline is not represented in this repository (U1, see the primary doc).

## 12. Gaps

| ID | Item |
|---|---|
| WS7-G12 | Worker's double Playwright install (venv-level + frontend-scoped): unclear whether both are needed |
| — | Root `Dockerfile` maintenance burden: unreferenced, untested by CI's `docker` job, could silently rot |

## Agent context and remaining work

- **Read:** the three Dockerfiles, `.dockerignore`, `deploy/start.sh`, `docs/RC022_BUILD_RELEASE_STAGING.md`.
- **Allowed:** `Dockerfile`, `Dockerfile.api`, `Dockerfile.worker`, `.dockerignore`.
- **Tests:** `tests/test_rc022_build_release_contract.py`; a local `docker build` for either runtime image before merging a Dockerfile change (not run in Phase 2).
- **Prohibited:** no `docker push`; no changes that copy `.env*`, `frontend/dist`, or secrets into an image; no removing the non-root `USER runr` step.
- **Registry:** part of `deployment-release-ci` (primary doc).
- **Ticket candidates:**
  1. Decide whether to delete the unreferenced root `Dockerfile` or keep it as a documented local-only compatibility path (currently undocumented risk of silent rot).
  2. Clarify or remove the worker's duplicate Playwright install (WS7-G12).
