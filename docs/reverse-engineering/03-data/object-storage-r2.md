> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Object storage: local filesystem and S3-compatible (Cloudflare R2)

This is a secondary doc of the 03-data group; the group primary is [schema-and-migrations.md](schema-and-migrations.md) and the WS-5 subsystem primary is [domain-model.md](../01-architecture/domain-model.md). LIVE PRODUCTION = UNKNOWN. No bucket was contacted. Env keys appear as names only.

## 1. Purpose and capabilities

Private binary objects (run artifacts, candidate uploads, CV editor assets, bulk exports) go through one `ObjectStorage` protocol (`backend/storage/base.py:26-50`: `put`, `get`, `delete`, `exists`, `signed_download_url`). There are two implementations:
- `LocalObjectStorage`, for development and tests.
- `S3ObjectStorage`, generic S3 via `boto3`/`botocore`. R2 is reached only through its S3-compatible endpoint; there is no Cloudflare SDK.

The related contract doc `docs/RC021_PORTABLE_ARTIFACT_STORAGE.md` was checked against code: defaults (512 MiB, 24 h, 100 MiB) and behavior match `backend/storage/materialization.py` and `backend/storage/policy.py`.

## 2. Owned paths (`backend/storage/`, 9 files)

`__init__.py` (41), `base.py` (50), `factory.py` (41), `keys.py` (61), `local.py` (172), `s3.py` (187), `materialization.py` (193), `policy.py` (107), `readiness.py` (72).

## 3. Entry points

| Entry point | Code | Invoked by |
|---|---|---|
| `create_object_storage(environ)` | `backend/storage/factory.py:12` | `backend/bootstrap.py:330`; `backend/adapters/stage_adapters.py:350` |
| `probe_object_storage()` | `backend/storage/readiness.py:21` | `backend/api/routes/system.py:87` (readiness route, WS-1) |
| Signed local object download | `LocalObjectStorage.verify_signed_download` (`backend/storage/local.py:150`) | Unauthenticated route `storage.objects` GET prefix `("storage","objects")`, registered at `backend/api/routes/storage.py:23` (WS-1) |
| `publish_file_artifacts(storage, run_id, artifacts)` | `backend/storage/materialization.py:148` | stage engine → artifact publisher (WS-2) |
| `materialize_object(...)` | `backend/storage/materialization.py:108` | renderers needing a file path; `ObjectMaterializationSession` used at `backend/adapters/stage_adapters.py:350` |
| `validate_object_download(...)` | `backend/storage/policy.py:72` | callers before signing or serving (RC-021) |

## 4. Backend selection

`create_object_storage(environ)` (`backend/storage/factory.py:12-41`) calls `validate_environment` first. `OBJECT_STORAGE_BACKEND=local` gives `LocalObjectStorage`; **any other valid value (`s3` or `r2`) gives `S3ObjectStorage`**.

`backend/bootstrap.py:321-330`: when the backend is `local` and `OBJECT_STORAGE_LOCAL_ROOT` is unset (or bootstrap-managed), the root is forced to `<data_dir>/objects` and written back into `os.environ` with marker `RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT=1`.

| Env key (name only) | In `ENV_SCHEMA` | Default | Used by |
|---|---|---|---|
| `OBJECT_STORAGE_BACKEND` | yes | `local` | factory, bootstrap; production must be `s3`/`r2` |
| `OBJECT_STORAGE_LOCAL_ROOT` | yes | `.backend_storage/objects` | local |
| `OBJECT_STORAGE_CACHE_ROOT` | yes | `.backend_storage/cache` | materialization (`materialization.py:30-31`) |
| `OBJECT_STORAGE_CACHE_MAX_BYTES` / `OBJECT_STORAGE_CACHE_MAX_AGE_SECONDS` | yes | 536870912 / 86400 | cache pruning |
| `OBJECT_STORAGE_MAX_DOWNLOAD_BYTES` | yes | 104857600 | `policy.py:66-69` |
| `LOCAL_OBJECT_STORAGE_BASE_URL` / `LOCAL_OBJECT_STORAGE_SIGNING_SECRET` | yes | loopback `/v1/storage/objects` URL / dev fallback string in `factory.py:28` | local signed URLs |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` | yes | none (required for s3/r2 or production) | S3 |
| `S3_REGION` | yes | `auto` (R2) | S3 |
| `S3_SIGNED_URL_TTL_SECONDS` | yes | 900 | both backends |
| `S3_CONNECT_TIMEOUT_SECONDS`, `S3_READ_TIMEOUT_SECONDS`, `S3_MAX_ATTEMPTS` | **no** | 3 / 15 / 2 | `s3.py:28-39` botocore config (SigV4, standard retries) |

## 5. Object key layout

`build_private_object_key` (`backend/storage/keys.py:44-61`) produces:
```
private/<namespace>/<owner_id>/<category>/<object_id>/<filename>
```
Each segment is NFKC-normalized. Characters outside `[A-Za-z0-9._-]` become `_`. If the segment was altered or is longer than 120 characters, it is truncated and a 10-hex SHA-256 suffix is added (L32-41). `normalize_object_key` rejects empty, absolute, NUL, `.` and `..` segments (L15-30).

| Namespace | Writer | Shape |
|---|---|---|
| `runs` | `publish_file_artifacts` (`materialization.py:148-193`) | `private/runs/<run_id>/<artifact_type>/<artifact_id>-<sha256[:16]>/<file>` plus metadata `run_id, artifact_id, artifact_type, content_sha256, file_name` |
| `users` | `backend/api/server.py:4983`, `:5011`, `:6004`; `backend/profiles/cv_editor.py:419`; `backend/profiles/cv_upload_jobs.py:237` | `private/users/<user>/<category>/<id>/<file>` (categories set by WS-1/WS-4 callers; not enumerated) |
| `health` | `probe_object_storage` (`readiness.py:30-36`) | `private/health/ready/probe/<uuid>/probe.txt`, deleted after the probe |

Company logos: the storage target for imported logos was not traced to a `build_private_object_key` call in this scope (WS-3 owns `backend/application/company_logo*.py`). UNKNOWN whether they use object storage or URLs.

Local physical layout (`backend/storage/local.py:42-69`): `root/<h0-2>/<h2-4>/<h4-32>` where `h = sha256(normalized_key)`. That is a 32-hex prefix, kept Windows-path-safe since `ee5b113a`. Reads fall back to the legacy full-digest path and the legacy key-as-path layout. The S3 key is the normalized key itself inside the bucket.

## 6. Call and data flows

- **Publish**: stage engine → `publish_file_artifacts`. It validates the download policy before upload, so oversized or unapproved files are never stored as artifacts. The content-hash key means a changed file never reuses a stale key.
- **Download**:
  - S3/R2 (`supports_direct_download = True`, `s3.py:67`): a presigned `get_object` URL with `ResponseContentDisposition` attachment and TTL (`s3.py:162-187`).
  - Local (`supports_direct_download = False`): HMAC-SHA256 over `key\nexpires\nfilename` gives `<base_url>/<key>?expires&signature[&download]` (`local.py:125-148`). It is verified by `verify_signed_download` (L150-172, constant-time compare) behind the unauthenticated `storage.objects` GET prefix (`backend/api/routes/storage.py:23`, WS-1). That route returns 404 when the backend has no verifier.
  - Per RC-021, callers run `validate_object_download` before signing or serving.
- **Materialize** (for renderers that need a file path): `materialize_object` (`materialization.py:108-128`) writes atomically (temp file, fsync, replace) into `<cache_root>/<sha256(key)[:20]>/<basename>`. It prunes by age, then oldest-first by size, protecting the target. `ObjectMaterializationSession` memoizes per run/request (used at `backend/adapters/stage_adapters.py:350`).
- **Readiness**: a put/get/delete probe on a daemon thread with a timeout (≤30 s) (`readiness.py:21-72`), called from `backend/api/routes/system.py:87`.

## 7. Invariants and failure handling

- Errors are wrapped: `ObjectStorageError`, `ObjectNotFoundError` (S3 404/NoSuchKey/NotFound, `s3.py:57-65`), `InvalidObjectKeyError`, `ObjectDownloadRejected`.
- `S3ObjectStorage` refuses blank bucket, endpoint or keys (`s3.py:80-90`). A missing `boto3` raises a clear `RuntimeError` (L20-26).
- A probe timeout leaves the daemon thread running and may leave a probe object behind if `delete` never runs; `delete` is attempted in `finally`.
- The dev signing secret fallback is not rejected by production validation, but production cannot use `local` (`backend/config/env_schema.py` production rule), so the fallback is not reachable there by config.
- **Deployment limitation (from RC-021 doc):** R2 signed redirects need bucket CORS for the frontend and extension origins. Bucket configuration is outside the repo, so its state is UNKNOWN.

## 8. Local data locations (T08)

`.backend_storage/` (untracked; gitignored by `.gitignore:30` `.backend_*` and `:37`) holds the local object root and cache defaults. The `<data_dir>/objects` fallback lives under `.backend_data/` (untracked; `.gitignore:32`). Both may contain private user documents. Ticket T08 (owner) covers vaulting them. Contents were not inspected.

## 9. Tests and safe verification (not executed in Phase 2)

`tests/test_object_storage.py` has 13 tests, all offline:
- key safety (L65-82)
- Windows path limit (L90)
- legacy layout (L102)
- lifecycle (L115)
- scoped signed URLs (L140)
- factory (L164)
- materialization (L178-212)
- bounded probe (L235)
- S3 with an injected fake client (L262)
- R2 factory (L297)

L313 is named "real R2" but uses `_FakeS3Client`.

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_object_storage.py tests/test_env_config.py
```
Safe verification commands, not executed in Phase 2. Never run against real `S3_*` credentials during documentation work.

## 10. Historical decisions and supporting commits

`git log --oneline 58a96674 -- backend/storage/` (7 commits, oldest last):

| Commit | Subject | Decision |
|---|---|---|
| `c7bf7cbd` | deoployment prep initial setup (introduced the storage package and `s3.py`) | S3/R2 backend foundation |
| `7d382067` | Store career inventory as JSONL, dedupe, tracker | early data storage |
| `d6018c3e` | production busg resolution for render turso r2 | production storage fixes |
| `41e9a616` | [CP-037R] … final integration | evidence-backed documents into object storage |
| `ee5b113a` | fix(storage): keep local object paths Windows-safe | 32-hex sharded local layout |
| `7251ae29` | feat(acquisition): reconcile producers inputs and runtime data (RC-021 cache/download limits, `supports_direct_download`) | bounded cache + presigned downloads |

## 11. Current implementation status

| Capability | Classification |
|---|---|
| Local/S3 backend selection | VERIFIED (scope: static `factory.py:20-41`, `bootstrap.py:321-330`) |
| R2 via S3 endpoint + presigned downloads | IMPLEMENTED-UNVERIFIED (fake-client tests only) |
| Local HMAC signed downloads | VERIFIED (scope: static — signer `local.py:125`, verifier `:150`, route registered `storage.py:23`) |
| Bounded materialization cache / download policy | IMPLEMENTED-UNVERIFIED |
| Readiness probe | IMPLEMENTED-UNVERIFIED |

### Deployment evidence (documentary only)
- `render.yaml` api/worker set `OBJECT_STORAGE_BACKEND=r2` and `S3_REGION=auto`, with `S3_*` credentials `sync: false`.
- `docs/deployment/render.md` L96-97 show an R2 endpoint placeholder.
- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (2026-09-11) records an R2 write/read/delete probe passing.

Current bucket state is UNKNOWN.

## 12. Confirmed gaps and unresolved questions

| ID | Item |
|---|---|
| WS5-O1 | S3 timeout/attempt env keys are missing from `ENV_SCHEMA` (part of WS5-G4) |
| WS5-O2 | R2 bucket CORS for signed redirects is unverifiable from the repo |
| WS5-O3 | Company-logo storage target not traced (WS-3) |
| WS5-O4 | A readiness probe timeout can orphan a `private/health/...` object; no sweeper found |
| T08 | Local `.backend_storage/` vault (owner) |

## Agent context and remaining work

**(a) Agent context packet**
- Required reading: this doc; [schema-and-migrations.md](schema-and-migrations.md) (group primary); [domain-model.md](../01-architecture/domain-model.md); `docs/RC021_PORTABLE_ARTIFACT_STORAGE.md` (checked, matches code); `backend/storage/{base,factory,keys,local,s3,materialization,policy,readiness}.py`.
- Allowed paths: `backend/storage/**` (9 files).
- Tests to run: `.venv\Scripts\python.exe -m pytest -q tests/test_object_storage.py tests/test_env_config.py` (safe verification commands, not executed in Phase 2).
- Prohibited: contacting any bucket or using real `S3_*`/`LOCAL_OBJECT_STORAGE_SIGNING_SECRET` values; changing the key layout (existing objects depend on it, including legacy fallbacks); removing the legacy read paths; weakening `validate_object_download`.

**(b) Registry proposal** (slice row; the WS-5 subsystem row is in [domain-model.md §Agent context](../01-architecture/domain-model.md#agent-context-and-remaining-work))

| id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `object-storage` | Object storage (local / S3 / R2) | `backend/storage/**` | `docs/reverse-engineering/03-data/object-storage-r2.md` | `tests/test_object_storage.py`, `tests/test_env_config.py` | WS-5 |

**(c) Gap and ticket candidates**
1. Add `S3_CONNECT_TIMEOUT_SECONDS`/`S3_READ_TIMEOUT_SECONDS`/`S3_MAX_ATTEMPTS` to `ENV_SCHEMA` (WS5-O1, WS5-G4).
2. Document required R2 bucket CORS in the deploy docs (WS5-O2; with WS-7).
3. Trace the company-logo storage target (WS5-O3; WS-3).
4. Add a sweeper or TTL for orphaned `private/health/` probe objects (WS5-O4).
5. T08 local-data vault (owner; existing ticket).
