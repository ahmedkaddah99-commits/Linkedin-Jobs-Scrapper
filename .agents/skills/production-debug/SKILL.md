---
name: production-debug
description: Production-first bug diagnosis and fixing for the Runr app. Use when the user reports a production bug, Render failure, frozen run, failed fetch, missing generated document, provider integration issue, or says local fixes are not enough. Forces live visibility checks across Render, Turso, Cloudflare R2/S3, Clerk, ScrapeOps, DeepSeek, Creem, and frontend configuration before and after code changes.
---

# Production Debug

## Core Rule

Treat production as the source of truth. A local test is necessary but not sufficient when the user reports a production issue.

Do not call a fix complete until you have one of these:

- Live production evidence that the issue is fixed.
- A specific blocked reason explaining exactly which production surface is not visible and what credential/token/log/screenshot is missing.

Never print secrets. Only report key presence, provider names, safe IDs, counts, statuses, timestamps, and redacted error bodies.

## Workflow

1. Restate the production symptom in binary terms.
   Example: "Run X must either produce at least one usable document artifact or fail with a specific error; it must not remain queued/running forever or complete with zero output."

2. Establish visibility before editing.
   Run `scripts/check_production_access.py` from this skill when provider access matters. Use `user_config/.env` as the authoritative backend env unless the user says otherwise.

3. Pull production facts.
   For run bugs, collect:
   - Render API and worker logs around the run window.
   - Turso rows for `runs`, `run_stage_results`, `run_jobs`, `run_job_sets`, `artifacts`, and `reviews`.
   - R2 object existence for expected artifact object keys if relevant.
   - Frontend API target and browser error details if the symptom is `Failed to fetch`.

4. Find the invariant that production violated.
   Prefer statements like:
   - "completed run must have required artifacts"
   - "queued run must be claimable by a live worker"
   - "frontend must not hide backend failure behind generic fetch error"
   - "provider failure must be persisted in run/stage error fields"

5. Patch the code with production behavior in mind.
   Add focused tests that reproduce the production invariant, not only the local happy path.

6. Verify locally and against production.
   Local verification: run focused tests.
   Production verification: after deployment, query Render deploy status/logs and live app/provider state. If deployment is not performed in the current turn, state the exact post-deploy checks to run and do not claim production is fixed yet.

## Production Access Script

Use:

```powershell
$SkillRoot = ".agents\skills\production-debug" # or ".cline\skills\production-debug" / ".codex\skills\production-debug"
python "$SkillRoot\scripts\check_production_access.py" --env user_config\.env
```

The script is read-only except for a tiny R2/S3 write-read-delete probe. It does not print secret values.

Use `--skip-r2-write` if object storage writes would be unsafe for the task.

## Required Evidence By Bug Type

Run freezes or missing output:

- Render worker logs for the specific `run_id`.
- Turso run row with status, timestamps, `last_error`.
- Stage rows and metrics.
- Generated job count and artifact count.
- If status is `completed`, prove required output exists.

Failed to fetch:

- Browser Network status/error if available.
- Render API logs for matching timestamp.
- API health/readiness result.
- Frontend `VITE_API_BASE_URL` or equivalent deployed value.

Provider failure:

- Provider env presence.
- Provider read-only API probe result.
- App log entry that records the provider error without leaking credentials.

Slow page or API timeout:

- Capture the exact reproduction window in UTC and the affected `run_id` when available.
- Run the production access script with `--log-start`, `--log-end`, and `--run-id`.
- Compare browser timeout duration with Render route timing and structured phase timing.
- Identify the dominant backend phase before changing frontend timeout or loading behavior.
- Trace that phase's call graph for unscoped scans, repeated remote reads, object downloads, parsing, or writes performed by a GET request.
- Preserve content correctness: uploaded files are deduplicated only by a persisted content hash, never by filename.
- Add regression tests that fail if a scoped endpoint calls global collectors, downloads object contents, mutates persisted data, or reloads data already available to the caller.
- After deployment, repeat the same production window check and compare route and phase timings against the pre-fix baseline.

Deployment mismatch:

- Git diff/commit expected to be deployed.
- Render latest deploy ID/status for API and worker.
- Runtime logs proving the new code path is active.

## Slow Request Command

Use exact UTC timestamps covering the browser reproduction:

```powershell
$SkillRoot = ".agents\skills\production-debug" # or ".cline\skills\production-debug" / ".codex\skills\production-debug"
python "$SkillRoot\scripts\check_production_access.py" `
  --env user_config\.env `
  --log-start 2026-06-22T07:25:00Z `
  --log-end 2026-06-22T07:50:00Z `
  --run-id run_example `
  --skip-r2-write
```

Treat the output as a comparison of layers:

1. Browser duration and aborts.
2. Render route duration.
3. Structured endpoint phase timings such as `customer_view_payload_timing`.
4. Turso query health and run state.
5. R2 object existence and provider health.

Do not recommend deleting or consolidating infrastructure until the dominant phase is proven to be infrastructure-bound after its application call graph has been scoped.

## Blocker Standard

If a production surface is not visible, name it exactly and say what is needed:

- "Render logs blocked: missing or invalid `RENDER_API_KEY`."
- "Browser failure blocked: need Network tab status/response or an in-app diagnostic bundle."
- "Google OAuth live probe blocked: need user OAuth token/session flow; static client config is not enough."

Do not proceed as if blocked data was checked.

## References

Read `references/runr-production-surfaces.md` when provider-specific details or table names are needed.
