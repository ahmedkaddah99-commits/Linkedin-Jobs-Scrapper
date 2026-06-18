# Production Readiness Implementation Status

Date: 2026-06-18

## Implemented In This Tranche

- Database connection abstraction for local SQLite and remote Turso.
- Repeatable migration command and migration status support.
- Environment contract and sanitized development examples.
- Local and S3-compatible object-storage implementations.
- Frontend absolute API URL handling.
- Docker runtime and role-based startup commands.
- Render Blueprint scaffolding.
- CI scaffolding.
- Deployment and runtime documentation.

## Explicitly Not Performed

- Creating Turso, Render, Cloudflare, Clerk, or LemonSqueezy resources.
- Importing the live SQLite database into Turso.
- Uploading current local assets into R2.
- Changing DNS.
- Replacing every filesystem call site with object storage.
- Replacing the standard-library API server with FastAPI/Uvicorn.
- Bulk untracking generated files from the existing dirty Git worktree.

## Why Bulk Untracking Is Deferred

The worktree contained extensive user changes before this tranche began. There
are hundreds of tracked generated/runtime files. Running broad
`git rm --cached` commands now would mix a large unrelated index mutation into
the user's active work.

After the active work is committed or moved to a clean branch, review tracked
ignored files with:

```powershell
git ls-files -ci --exclude-standard
```

Then remove only reviewed paths from Git tracking while preserving local files:

```powershell
git rm -r --cached -- "test CV"
git rm -r --cached -- generated_docs
git rm -r --cached -- backend/config/outputs
```

Do not run those commands without reviewing the exact tracked paths first.

## Next Code Iterations

1. Integrate object storage into candidate uploads and profile photos.
2. Integrate object storage into generated artifacts and downloads.
3. Harden queue claiming, leases, shutdown, and retry idempotency against
   Turso.
4. Add Turso-backed integration tests using a disposable development database.
5. Migrate the HTTP transport to FastAPI/Uvicorn with response-contract tests.
6. Perform cloud provisioning and production data cutover.
