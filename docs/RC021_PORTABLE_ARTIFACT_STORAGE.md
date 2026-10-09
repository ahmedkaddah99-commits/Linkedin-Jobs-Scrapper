# RC-021 — Portable artifact storage

RC-021 keeps final worker artifacts portable across hosts and makes the local
object cache disposable.

## Contract

- Stage artifacts are published before persistence by the existing stage-engine
  publisher. File object keys include a content hash, so a changed artifact
  cannot reuse a stale key.
- Candidate uploads and bulk-export bundles carry object size/content metadata.
- With S3/R2, authenticated artifact and candidate downloads return a short-
  lived signed redirect. The API does not read the whole object or count the
  object body as API response bytes. The timing log records
  `object_storage_bytes_shifted`; the redirect exposes `X-Runr-Object-Bytes`.
- Local storage keeps the existing byte-serving behavior for development and
  tests. Its signed-object endpoint validates HMAC, filename, expiry, MIME,
  and size before serving bytes.
- Local materialization is bounded by `OBJECT_STORAGE_CACHE_MAX_BYTES` and
  `OBJECT_STORAGE_CACHE_MAX_AGE_SECONDS`. Defaults are 512 MiB and 24 hours.
  A missing cache entry is rehydrated from object storage.
- Downloads are limited by `OBJECT_STORAGE_MAX_DOWNLOAD_BYTES` (default 100
  MiB) and a safe document MIME/extension policy.

## Verification

Offline tests:

```text
tests/test_phase_a_rc021.py       6 passed
tests/test_object_storage.py      13 passed, 4 subtests passed
selected backend API downloads    3 passed
frontend/src/lib/api.test.js      21 passed
```

The full `tests/test_backend_api.py` run reached 123 passed, 2 unrelated
baseline failures, and 14 subtests passed. The failures were the existing
tracker filename expectation and ATS attempt-history expectation; neither
touches RC-021 storage/download code.

## Deployment limitation

S3/R2 signed redirects require the bucket's CORS policy to allow the deployed
frontend/extension origins and expose normal download headers. Configuring a
bucket or provider was intentionally not performed in this offline ticket.

## Rollback

Revert only the RC-021 files listed by `git diff --name-only` for this ticket:
the storage policy/materialization/local/S3 files, portable download route
changes, `backend/api/routes/storage.py`, the cache env-schema entries, the
RC-021 focused tests, and this document. Preserve the pre-existing dirty
exporter, acquisition, RC-018, RC-019, and RC-020 changes. After rollback,
local downloads use the prior file/materialization path and existing object
keys remain readable.
