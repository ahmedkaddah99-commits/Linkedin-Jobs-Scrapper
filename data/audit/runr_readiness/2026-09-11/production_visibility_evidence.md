# Production visibility evidence

Captured on 2026-09-11 using the local `production-debug` access probe with `user_config/.env`. Secret values are intentionally omitted.

## Verified

- Render API key present; `runr-api`, `runr-worker`, and `runr-frontend` services visible.
- Render API, worker, and frontend live deployments are on commit `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553`.
- Turso credentials present; query succeeded; 110 tables visible.
- Cloudflare R2 credentials present; the probe was skipped in this audit invocation because the request was read-only. The migration transcript records the earlier authorized R2 write/read/delete probe as passed.
- Clerk credentials present; JWKS resolved with one key and `/v1/users?limit=1` succeeded.
- ScrapeOps key present; usage endpoint and proxy health succeeded.
- DeepSeek key present; bounded chat probe succeeded.
- Creem credentials present; discounts probe succeeded against `test-api.creem.io`.
- Frontend origin returned HTTP 200 and HTML.

## Operational blocker separate from data quality

- `frontend.api_proxy_health` failed because the deployed frontend bundle exposed an API host rendered as `${n}`; this must be repaired or rechecked before relying on the customer Jobs UI.
- An authenticated customer Jobs UI/feed check was not possible without a signed-in browser session.
- The latest acquisition cycle in Turso is `degraded` with `partial_source_coverage`, zero fresh observations, and 47 jobs published from the existing source-backed state. This is why the current head can be record-complete while the acquisition catalog remains incomplete.

## Not included

No provider secret, `.env`, bearer token, VPS environment file, production database, state database, production log, or browser session was copied into the audit bundle.
