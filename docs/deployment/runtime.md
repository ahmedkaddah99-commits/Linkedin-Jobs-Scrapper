# Production runtime

For the authoritative deployment topology and release-state record, see the
[WS-7 release-process record](../reverse-engineering/02-deployment/release-process-and-production-records.md).

The production API and worker images use Python 3.12 and include the runtime dependencies needed by the current application:

- Node.js and the locked frontend packages
- Playwright Chromium and its Linux libraries
- Tesseract OCR with English and German language data
- LibreOffice Writer for headless document conversion
- Python packages from `requirements-linux.txt`

The API and worker use separate production images (`Dockerfile.api` and
`Dockerfile.worker`) with overlapping but role-specific dependencies. The API
image runs the API-owned pre-deploy migrations; the worker image runs the
continuous worker. Keep the two image build inputs aligned when shared runtime
dependencies change.

## Build and inspect the images

```bash
docker build -f Dockerfile.api -t runr-api:local .
docker build -f Dockerfile.worker -t runr-worker:local .
docker run --rm runr-api:local node --version
docker run --rm runr-api:local python --version
docker run --rm runr-api:local tesseract --version
docker run --rm runr-api:local libreoffice --version
```

Each image runs as the unprivileged `runr` user. Runtime files under `.backend_data` are ephemeral in Render; production data must therefore use Turso, and persistent artifacts must use object storage rather than the container filesystem.

## Runtime roles

`deploy/start.sh` is the common entrypoint:

```bash
./deploy/start.sh api
./deploy/start.sh worker
./deploy/start.sh migrate
```

Role behavior:

| Role | Command |
| --- | --- |
| `api` | Starts `workspace_runner.py serve-api` on `0.0.0.0:$PORT`. |
| `worker` | Starts the continuous lease-aware worker and is the only production queue consumer. |
| `migrate` | Runs `python -m backend.database.migrate`; Render invokes it only as the API pre-deploy command. |

The startup script retains `process-next` for local/manual diagnostics. It must
not be configured as a production service or schedule while `runr-worker` is
active because it also claims queued runs.

Shared runtime settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `RUNR_DATA_DIR` | `.backend_data` | Local runtime directory used by the current CLI. |
| `RUNR_STORAGE_BACKEND` | `sqlite` | Current CLI storage selector. Turso remains SQLite-compatible and is configured separately by URL/token. |
| `RUNR_LOG_LEVEL` | `INFO` | CLI log level. |
| `WORKER_ID` | Role-specific | Stable worker identity for leases and logs. |
| `PORT` | `8000` | API listen port supplied by Render. |

Additional positional arguments are passed to the selected CLI role. For example:

```bash
./deploy/start.sh worker --sleep-seconds 10 --lease-seconds 120
```

## Local container smoke test

After configuring the development environment:

```bash
docker run --rm \
  -p 8000:8000 \
  --env-file dev.env \
  runr-api:local ./deploy/start.sh api
```

Then verify:

```bash
curl --fail http://127.0.0.1:8000/health/ready
```

Do not copy `.env`, `dev.env`, local databases, uploads, generated documents, or browser screenshots into the image. `.dockerignore` excludes these paths.
