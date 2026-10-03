> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Security, authentication and non-billing integrations (WS-6)

This doc covers how Runr checks identity and permissions, how it keeps sensitive data out of logs, how secrets are handled, how extension origins are checked, the SSRF guards around career-URL discovery, and the ScrapeOps integration. Creem billing is covered in [../05-subsystems/billing-and-creem.md](../05-subsystems/billing-and-creem.md). HTTP routing and handler plumbing belong to WS-1: [backend-api.md](backend-api.md).

No secret values, webhook secrets, product IDs, Render IDs or host identifiers appear here. Environment variables are listed by name only.

---

## 1. Purpose and user-facing capabilities

| Capability | What the user sees |
|---|---|
| Clerk sign-in | The web app signs in with Clerk. The frontend asks Clerk for a JWT from the `runr_backend` template (`frontend/src/context/SessionContext.jsx:121`, `frontend/src/lib/api.js:8`) and sends it as `Authorization: Bearer`. |
| Legacy API tokens | Opaque `bkat_…` tokens stored as PBKDF2 hashes, created through admin-scope routes. The code still accepts them as a "Clerk migration window" fallback. |
| Role/scope authorization | `admin`/`user` roles come from Clerk `publicMetadata.role`. Each role maps to a fixed scope set, and routes call `_require_scope` / `_require_admin`. |
| Account lifecycle | The Clerk webhook creates, updates and deactivates users. Self-service `DELETE /account` deactivates the user and cancels subscriptions. |
| Assisted Apply extension connection | A one-time, PKCE-bound connection that issues an `aases_…` session token tied to an exact `chrome-extension://` origin. The token is consumed by `assisted-apply` routes (WS-9). |
| CORS / origin policy | Exact allowlist for web origins. Extension origins are accepted only on the extension routes. |
| Log privacy | Recursive redaction of CV text, prompts, secrets, emails and phone numbers in worker logs, CLI diagnostics and acquisition audit payloads. |
| Secret references | `${secret:<id>}` / `${env:<NAME>}` placeholders are resolved at runtime from the secret store or the environment. |
| Career-URL discovery protection | The HTTP endpoint is hard-disabled (403). Connector-level public-HTTPS URL guard. |
| ScrapeOps proxy | Paid proxy fetches with a credit guard, health probe, bounded retries, redacted logs and a per-user usage summary (`GET /scrapeops/usage`). |

## 2. Owned paths and governing instructions

### Owned (exact file lists at `58a96674`)

| Path | Files | Lines | Role |
|---|---:|---:|---|
| `backend/integrations/__init__.py` | 1 | 53 | Re-exports Clerk and Creem helpers. ScrapeOps is not re-exported. |
| `backend/integrations/clerk.py` | 1 | 588 | JWT verification (JWKS), Clerk Backend API, Svix webhook verification, role→scope maps |
| `backend/integrations/creem.py` | 1 | 361 | Creem API, webhook/redirect signatures (see billing doc) |
| `backend/integrations/scrapeops.py` | 1 | 725 | ScrapeOps proxy params, envelope parsing, health check, retry, usage API |
| `backend/security/__init__.py` | 1 | 22 | Re-exports auth and secrets helpers |
| `backend/security/auth.py` | 1 | 186 | PBKDF2 token hashing, `ROLE_DEFAULT_SCOPES`, token issue/expiry/scope checks |
| `backend/security/redaction.py` | 1 | 135 | `redact_sensitive_data`, `RedactingFilter`, `public_run_summary` |
| `backend/security/secrets.py` | 1 | 58 | `${secret:…}` / `${env:…}` reference resolution |

Totals: `backend/integrations/**` has 4 files and `backend/security/**` has 4 files.

### Consumed, not owned (cited for flows)

`backend/api/server.py` (auth context, CORS, webhook handlers; WS-1), `backend/api/routes/route_support.py`, `backend/api/routes/admin.py`, `backend/api/routes/workspace.py`, `backend/application/assisted_apply_service.py` (WS-9/WS-4), `backend/application/domain_services.py`, `backend/config/env_schema.py`, `backend/config/plans.py`, `backend/worker/logging_config.py`, `backend/acquisition/audit.py`, `backend/connectors/company_career_sites.py` (WS-3).

### Governing instructions and existing docs

| Doc | Checked against code? | Verdict |
|---|---|---|
| Root `AGENTS.md` | Not re-read in detail for this scope | Governing repo instructions |
| [../../security/runr_data_ownership.md](../../security/runr_data_ownership.md) | Partly. Workspace/run ownership invariants match `user_can_access_workspace` usage in `admin.py:83,296` and `workspace.py:393`. The migration name `014_workspace_ownership` exists in `sqlite_migrations.py:3296`. | Accurate for the parts checked. Link it for the ownership model. |
| [../../legal/RUNR_TERMS_AND_CONDITIONS.md](../../legal/RUNR_TERMS_AND_CONDITIONS.md), [../../legal/RUNR_USER_AGREEMENT.md](../../legal/RUNR_USER_AGREEMENT.md) | Not verifiable against code (legal text). Contains `[INSERT …]` placeholders (e.g. T&C L107, L174). | Draft legal text only; not a security spec. |
| [../../phase-c-feed-performance-security.md](../../phase-c-feed-performance-security.md) | Not re-verified (feed projection is WS-4) | Covers public projection stripping, not auth |
| [../../prd/scrapeops_usage_and_local_market_sourcing_prd.md](../../prd/scrapeops_usage_and_local_market_sourcing_prd.md), [../../scrapeops_usage_and_admin_dashboard_implementation_report.md](../../scrapeops_usage_and_admin_dashboard_implementation_report.md) | Not re-verified. The report title references the retired admin dashboard (C7, WS-11). | Historical/PRD, not authoritative |
| `backend/config/env_schema.py` | Yes (lines cited below) | Authoritative for env names and descriptions |

## 3. Entry points and registered routes

### HTTP (registered in `backend/api/routes/admin.py:23–33` unless noted)

| Route name | Method + path | `auth_required` | Security mechanism |
|---|---|---|---|
| `admin.auth.me` | GET `/auth/me` | True | `_auth_context` (Clerk JWT or legacy token) |
| `admin.webhooks.clerk` | POST `/webhooks/clerk` | **False** | Svix signature (`clerk.verify_webhook`). Origin policy skipped (`server.py:9232–9234`). |
| `admin.webhooks.creem` | POST `/webhooks/creem` | **False** | HMAC-SHA256 `creem-signature` (billing doc) |
| `admin.scrapeops` | GET `/scrapeops/*` (prefix, serves `scrapeops/usage` at `admin.py:82`) | True | Customer usage for the caller's own user. **Not an admin-only surface** (audit N-10). |
| `admin.settings`, `admin.settings.put` | GET/PUT `/settings` | True | `_require_identity` |
| `admin.account.delete` | DELETE `/account` | True | Typed confirmation `DELETE` or the account email (`admin.py:458–460`) |
| `admin.billing*` | see billing doc | mixed | — |
| `workspace.career_url_discovery` | POST `/career-url-discovery/*` (`workspace.py:33`) | True | Handler raises `PermissionError` unconditionally (`workspace.py:381–382`) → 403 |
| Assisted Apply extension routes | `backend/api/routes/assisted_apply.py:31–88` | mixed | Extension session + exact origin (WS-9 owns route details) |

**Unregistered residue (404 at baseline, C7):** the `admin.py` handler bodies for `users` (L113/127/132/346/351/430/494/500), `tokens` (L154), `secrets` (L177/196/363/436/505), `dashboard` (L102) and `analytics/events` (L239) are not registered in `register_routes`. Scope-protected token and secret management therefore has **no reachable HTTP surface** at baseline. `tests/test_customer_route_surface.py:4` guards this. Removal and residue are WS-11's `06-history-and-provenance/retired-features.md`.

### CLI / scripts

- `backend/scripts/migrate_users_to_clerk.py`: one-off migration of local users into Clerk (`create_user`, `find_user_by_email`, `find_user_by_external_id`). It needs `CLERK_SECRET_KEY` and makes network calls to Clerk.
- `backend/tools/dump_run_diagnostics.py:97`: diagnostic output wrapped in `redact_sensitive_data`.
- `backend/tools/discover_company_careers.py`: career discovery CLI (the only live path, since the API route is disabled).

### Process startup

`backend/api/server.py:serve_api` (L9343–9367) runs `validate_environment()`, parses `BACKEND_ALLOWED_ORIGINS` and `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS`, then builds the handler (`build_handler`, L8611).

## 4. Inputs, outputs, storage and dependencies

### Environment variable names (values never recorded)

| Name | Where read | Purpose |
|---|---|---|
| `CLERK_SECRET_KEY` | `clerk.py:399` (`require_env`) | Clerk Backend API bearer |
| `CLERK_PUBLISHABLE_KEY` | `clerk.py:205` | Issuer host derived when `CLERK_ISSUER` is unset |
| `CLERK_ISSUER` | `clerk.py:202` | Expected JWT issuer (**not in `env_schema.py` or `render.yaml`**; see WS6-G2) |
| `CLERK_WEBHOOK_SECRET` | `clerk.py:536` | Svix signing secret |
| `CLERK_HTTP_TIMEOUT_SECONDS` | `clerk.py:226` | Clerk HTTP timeout (clamped 1–10 s) |
| `VITE_CLERK_PUBLISHABLE_KEY` | frontend build (`render.yaml:23`) | Frontend Clerk key |
| `BACKEND_ALLOWED_ORIGINS` | `server.py:9353` | Web CORS allowlist. In production a `*` is rejected (`env_schema.py:415–418`). The baseline value is set in `render.yaml:98–99` and is not copied here. |
| `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` | `server.py:9355`, `env_schema.py:193,420–433` | Exact extension origins. Required in production. No wildcard. |
| `APP_FRONTEND_ORIGIN` / `FRONTEND_ORIGIN` | `server.py:8967` | Checkout redirect origin |
| `RENDER_FRONTEND_EXTERNAL_HOSTNAME` | `env_schema.py:188` | Preview frontend host allowance |
| `SCRAPEOPS_API_KEY` | `scrapeops.py:303` (plus callers) | ScrapeOps key (`render.yaml:150` api, `render.yaml:239` worker, `sync: false`) |
| `RUNR_DISABLE_QUOTAS` | `server.py:7417`, `backend/application/quota.py:35`, `env_schema.py:267` | Local-dev quota bypass (§6 flags) |
| `RUNR_ENV`, `RUNR_TEST_MODE`, `RUNR_PRIVATE_TEST_DEPLOYMENT` | `env_schema.py`, `backend/bootstrap.py:358,384`, `backend/application/production_rollout.py:68–72` | Environment/test boundaries |

### Storage (schema owned by WS-5, [../03-data/schema-and-migrations.md](../03-data/schema-and-migrations.md))

- `users` (`clerk_user_id` unique partial index, `sqlite_migrations.py:138–140`), API tokens (hash plus prefix), secrets (`SecretRecord`; provider `env` or `stored`).
- `assisted_apply_connections` (`sqlite_migrations.py:823`, migration `016_assisted_apply_connections` at L3308). It stores only hashes of authorization codes and session tokens, plus lookup prefixes.
- `analytics_events` / ScrapeOps usage ledger, written by the worker (`backend/adapters/stage_adapters.py:141–165`).

### External dependencies

Clerk (`https://api.clerk.com/v1`, issuer JWKS), Svix (`svix` package optional, with a manual HMAC fallback), `cryptography` (RSA verify), ScrapeOps (`proxy.scrapeops.io`, `backend.scrapeops.io`), and the `httpbin.org/get` health-probe target (`scrapeops.py:22`).

## 5. Important call/data flows

### 5.1 Bearer auth resolution (`backend/api/server.py`)

1. `_auth_context` (L9091) takes the bearer token from `Authorization` (`route_support.py:_extract_bearer_token` L36). If there is none, it raises `PermissionError("Missing bearer token.")` → 401.
2. `_resolve_auth_context` (L7824):
   - **JWT-shaped token** (two dots). `_token_looks_like_clerk_jwt` (L7720) decodes the payload *without verifying it* and checks for `iss` containing "clerk", `sub` starting with `user_`, or `sid`+`exp`.
     - If the token is Clerk-like: check the in-process cache first (`_AUTH_CONTEXT_CACHE`, key = SHA-256 of the token, TTL 60 s, capped at `exp-5`, max 256 entries; L205–208, L7734–7794). Otherwise run `_build_clerk_auth_context` (L7659). On failure, raise `PermissionError` with **no legacy fallback** (L7855–7864).
     - If the token is JWT-shaped but not Clerk-like: try Clerk, and if that fails fall back to the legacy token lookup with a warning log (L7865–7889).
   - **Opaque token.** `_build_legacy_auth_context` (L7689) → `domain_services.authenticate_access_token` (L222–243) runs `verify_token_value` against candidate tokens (by prefix lookup, or all active tokens), skipping inactive or expired tokens and inactive users. It logs "Accepted legacy api_token fallback … during Clerk migration window" (L7893).
3. `_build_clerk_auth_context` → `clerk.verify_session_token` (L314–382):
   - Requires `alg == RS256` and a `kid`.
   - Issuer: if configured (`CLERK_ISSUER`, or the host decoded from `CLERK_PUBLISHABLE_KEY`) and the token has `iss`, they must match. **If nothing is configured, the token's own `iss` is used to locate JWKS** (L336–342; WS6-G2).
   - JWKS is fetched from `<issuer>/.well-known/jwks.json`, cached 300 s, and force-refreshed on an unknown `kid`.
   - PKCS1v15/SHA-256 signature check, then `exp` (only if present) and `nbf` with 5 s skew.
   - `azp` is checked **only** when `allowed_authorized_parties` is passed. `_build_clerk_auth_context` does not pass it (L7660; WS6-G3).
   - `role`, `plan_id` and `quota_overrides` come from `publicMetadata`, which the JWT template supplies (`env_schema.py:8–14 CLERK_SESSION_TOKEN_TEMPLATE_HINT`).
4. Local user lookup is by Clerk subject; if missing, it auto-provisions from the Clerk API or from the claims (`server.py:7640–7656`). The role is normalized to `admin`|`user`. `build_synthetic_token` assigns `_ADMIN_SCOPES` or `_USER_SCOPES` (`clerk.py:64–103,157–178`).
5. `_auth_context` rejects inactive users (L9099) and logs user ID and auth method (no token).

Guards built on the context (`server.py`):

| Guard | Line | Rule |
|---|---|---|
| `_require_identity` | 9110 | any valid context |
| `_require_clerk_identity` | 9114 | `auth_method == clerk_jwt` **and** normalized `azp` ∈ `BACKEND_ALLOWED_ORIGINS` set |
| `_require_scope` | 9125 | `token_has_scope` — `admin` scope implies every scope (`auth.py:184–186`) |
| `_require_acquisition_permission` | 9132 | application-level checker |
| `_require_admin` | 9140 | role `admin` **and** `admin` scope |

Error mapping: in `do_GET`/`do_POST`/`do_PUT` (L9193–9300), a `PermissionError` becomes 401 when the message matches `_is_unauthorized_permission_error` (`route_support.py:43–58`) and 403 otherwise.

### 5.2 Legacy API tokens (`backend/security/auth.py`)

`issue_api_token` (L149) creates `bkat_` + `token_urlsafe(32)` and stores a 14-character prefix plus `hash_token_value`, which is PBKDF2-SHA256 with 120,000 iterations and a 16-byte salt, formatted `iter$salt$digest` (L44, L123–126). `verify_token_value` compares in constant time (L129–140). `build_token_scope_set` merges role defaults (`ROLE_DEFAULT_SCOPES`, L47–116: admin/editor/reviewer/viewer) with explicit scopes. Explicit scopes are **not** capped by role (WS6-G6). Token expiry: `token_is_expired` treats an empty or unparseable value as not expired (L172–181).

### 5.3 Clerk webhook (`server.py:_handle_clerk_webhook_event` L8093–8172)

`clerk.verify_webhook` (L535–588) uses `svix.webhooks.Webhook` when importable. Otherwise it does a manual check: `svix-id`/`svix-timestamp`/`svix-signature` headers, ±300 s tolerance, HMAC-SHA256 over `id.timestamp.body` with the base64 secret (a `whsec_` prefix is stripped), and constant-time `v1,` comparison. Events:
- `user.created`: upsert by Clerk ID, or by email, or create a new `UserRecord(user_id=<clerk id>)`; set `clerk_user_id`; emit `user_signed_up` with only the email domain.
- `user.updated`: update email, name and role.
- `user.deleted`: deactivate the user and cancel subscriptions.
- Any other type is `ignored`.

### 5.4 Assisted Apply extension connection (`backend/application/assisted_apply_service.py`; routes WS-9)

TTLs (L26–28): request 10 min, authorization code 2 min, session 8 h.
1. The extension creates a request with a PKCE S256 challenge and its origin (`normalize_extension_origin` L73–78 requires `^chrome-extension://[a-p]{32}$`). The callback is `https://<id>.chromiumapp.org/runr/connect` (L81–85).
2. The signed-in web user authorizes (`authorize` L237–284). A pending request cannot be bound to another user. An `aaac_` code is issued and stored as a hash plus prefix.
3. `exchange` (L310–354) checks that the origin equals the bound origin, status is `authorized`, the code hash verifies, and PKCE `S256(verifier)` matches with `hmac.compare_digest`. It then issues an `aases_` + `token_urlsafe(48)` session stored as a hash. It is one-time because it is a repository state transition.
4. `authenticate_session` (L356–386) filters by session prefix plus exact origin plus `active` status plus hash verify plus active user, then touches `last_used_at`. `revoke_current` (L388+).
5. HTTP layer (`server.py`): `_request_client_origin` (L8950–8961) uses `Origin`. For originless extension service-worker requests it uses `X-Runr-Extension-Origin` **only on extension paths**, and any non-`chrome-extension` origin becomes empty. The service layer enforces the bound-origin match.

`assisted_apply_package_service.py:594,651` reuses `hash_token_value`/`verify_token_value` for document grant tokens (`X-Runr-Document-Grant` header allowed in CORS, `server.py:8750`).

### 5.5 CORS and origin policy (`server.py:8721–8763`, `route_support.py:85–149`)

- `_normalize_origin_value`: `chrome-extension://<32 a-p>` with no path/query/fragment, or `http(s)://netloc`. Anything else becomes empty.
- `_cors_origin`: an extension origin is allowed only when `_is_assisted_apply_extension_path()` (`/assisted-apply/extension/*` or exactly `/assisted-apply/telemetry/events`) **and** the origin is in the extension allowlist. Web origins are allowed if `allow_all_origins`, or in the allowlist, or **loopback** (`127.0.0.1`/`localhost`/`::1`, L8732; WS6-G4).
- `_enforce_origin_policy`: any request whose `Origin` is not allowed gets a 403. Webhook POSTs skip it (L9232–9234). Requests with no `Origin` header pass (non-browser clients).
- `_parse_allowed_origins` silently drops extension origins from the web list. `_parse_allowed_extension_origins` raises on `*` or non-exact values.

### 5.6 Log privacy (`backend/security/redaction.py`)

- `is_sensitive_key` (L62–64) matches exact keys (L13–41: tokens, API keys, authorization, CV/document/letter text, `email`, `phone`, `prompt*`, `secret*`, `stack_trace`, `error_message`, `last_error`, `token_hash`, …) and substrings (L42–53).
- `redact_sensitive_data` (L67–89) recurses through dataclasses, mappings and sequences. It re-parses JSON-looking strings, and a regex masks named JSON fields inside other strings (L54–59).
- `RedactingFilter` (L92–106) redacts `msg`, `args` and every non-standard `LogRecord` attribute. It is installed on the worker stream and file handlers (`backend/worker/logging_config.py:98,114`), and `WorkerJsonFormatter` redacts its payload (L64).
- `public_run_summary` (L109–126) exposes run metadata and counts only (`has_error` is a boolean, never the error text).
- Acquisition audit adds email, phone, bearer and query-secret regex masking on top (`backend/acquisition/audit.py:79–103`). It is applied when persisting (`sqlite_acquisition_audit.py:97,243`) and in a migration backfill (`sqlite_migrations.py:2791–2802`).
- ScrapeOps text: `sanitize_scrapeops_text` / `sanitize_url_for_logs` replace `api_key=` with `[redacted]` and `url=` with `[target]` (`scrapeops.py:139–162`). The usage records store the sanitized target URL (L282).
- The API auth logger emits user ID, auth method and error *type* only (`server.py:7797–7821`). However, the legacy-fallback warning includes the Clerk exception message (L7877–7881). The API process is not shown to install `RedactingFilter` on its own handlers (WS6-G5).

### 5.7 Secrets handling (`backend/security/secrets.py`)

`resolve_secret_references` (L44–58) walks dicts and lists. `${secret:<id>}` resolves through `secret_lookup` into a `SecretRecord`: provider `env` reads `os.getenv(env_var_name)`, provider `stored` returns the stored `secret_value` (L29–41). `${env:<NAME>}` reads the environment directly. A missing value raises `KeyError` naming the secret ID or env var name, never the value. It is used by `domain_services.py:339–342`. `SecretRecord.to_public_dict` is what the (unregistered) secret routes would return. Stored secrets are persisted in the DB **without encryption in this module** (WS6-G7). Deployment secrets are all `sync: false` in `render.yaml` (e.g. L126–150), so no values live in the Blueprint.

### 5.8 Career-URL discovery SSRF protections

- **API:** `POST /career-url-discovery/run` always returns 403 (`workspace.py:381–382`, commit `5a91380e`). `server.py:116` still imports `run_career_url_discovery`, but no reachable call exists.
- **Connector guard:** `company_career_sites.py:_is_public_https_url` (L517–535) accepts only `https`, with no userinfo. It rejects `localhost`, `*.localhost`, `*.local`, and literal IPs that are private/loopback/link-local/reserved/unspecified. **It does not resolve hostnames**, so a public DNS name pointing at a private IP passes (WS6-G8). It is used for academic listing links (L1026). WS-3 owns the connector.
- For comparison, `backend/application/company_logo.py:181–208` does resolve through `getaddrinfo` and checks each address (WS-3).
- The acquisition live-network gate is `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` (`backend/acquisition/network_policy.py:9–18`), set to `"false"` on Render (`render.yaml:84–85`).

## 6. Invariants, failure handling and recovery

### Invariants (as implemented)

1. A Clerk-like JWT that fails verification is never retried as a legacy token (`server.py:7855–7864`; test `test_clerk_like_jwt_failure_does_not_try_legacy_token_lookup`).
2. Raw tokens (API, authorization code, extension session, document grant) are never stored, only PBKDF2 hashes plus short lookup prefixes.
3. Extension sessions are bound to one exact origin and one user. Codes are one-time and expire after 2 min.
4. Production env validation rejects a wildcard web CORS setting and requires exact extension origins (`env_schema.py:410–433`).
5. Webhooks are unauthenticated by bearer token but always signature-verified before any state change (`admin.py:213–221`).
6. Inactive users are rejected in `_auth_context`, `authenticate_access_token` and `authenticate_session`.
7. Admin checks need both role and scope (`server.py:9140–9147`).

### Failure handling

- A Clerk JWKS/API network error raises `RuntimeError`, which becomes `PermissionError` (401/403). The Clerk HTTP error body is embedded in the exception message (`clerk.py:248–252`).
- A generic `Exception` from a handler returns 500 with `str(exc)` in the body (`server.py:9222–9224`). Provider error text can therefore reach clients.
- ScrapeOps: `classify_failure` (L431–479) maps 401 to out of credits, 403 to invalid key, 429 to concurrency, 400 to bad request, and 5xx to upstream. Billed statuses are 200 and 404 (L75–76). `scrapeops_request_with_retry` (L530–642) retries only on connection or timeout errors and statuses {0,408,429,5xx}, at most 5 retries, with backoff capped at 30 s per step and 120 s total. **Responses below 500 (including 429) return immediately without retry** (L567), so 429 is listed as retryable but never retried in practice (WS6-G9). The health probe (`check_scrapeops_proxy_health` L296–412) returns `healthy`/`banned_account`/`insufficient_credits`/`network_or_timeout_error`/`missing_api_key`/`proxy_unavailable`. `require_scrapeops_proxy_health` raises `ScrapeOpsProxyUnavailableError` before proxy-backed acquisition begins. LinkedIn targets log a credit-rate warning (L121–126).

### Auth bypass / dev-mode flags (recorded as requested)

| Flag / behaviour | file:line | Effect | Production guard? |
|---|---|---|---|
| `RUNR_DISABLE_QUOTAS` | `server.py:7417`, `backend/application/quota.py:35`, `env_schema.py:267–271` | Quota limit becomes -1 (unlimited). A **quota** bypass, not an auth bypass. | **None** in `get_environment_validation_errors` (`env_schema.py:380–435`) |
| `RUNR_TEST_MODE` / `RUNR_ENV=test` / `PYTEST_CURRENT_TEST` | `backend/bootstrap.py:358,384` | Test-bootstrap boundary. Rejects Turso, production and live network. | Fail-closed |
| `RUNR_PRIVATE_TEST_DEPLOYMENT` | `backend/application/production_rollout.py:68–72`; keys in `render.yaml:80,197` | Rollout-gate switch. Effect on auth not traced. | UNKNOWN |
| `BACKEND_ALLOWED_ORIGINS=*` | `route_support.py:128–137`, `server.py:8732` | Allow all web origins | Rejected when production (`env_schema.py:415–418`) |
| Loopback origins always allowed | `server.py:8732` | CORS for `localhost`/`127.0.0.1`/`::1` in every environment | None |
| Legacy opaque token fallback | `server.py:7891–7903` | Non-Clerk bearer tokens accepted ("Clerk migration window") | None (no sunset flag) |
| Unconfigured Clerk issuer → trust token `iss` | `clerk.py:336–342` | JWKS fetched from the token-supplied issuer | Depends on `CLERK_PUBLISHABLE_KEY` presence (schema `required: True`, `env_schema.py:123–127`). Enforcement of `required` at startup not verified. |
| `CREEM_API_BASE_URL` | `creem.py:29–34` | Provider base URL override | None (billing) |
| Webhook routes skip origin policy | `server.py:9232–9234` | By design | Signature-verified |

A search for `AUTH_BYPASS`, `DEV_AUTH`, `SKIP_AUTH`, `ALLOW_UNAUTH`, `INSECURE` and `RUNR_*DISABLE/ALLOW/DEV/BYPASS/SKIP/FAKE/MOCK/DEBUG` string literals under `backend`, `deploy` and `render.yaml` found **no explicit authentication-bypass flag**. The only hits were those listed above plus `RUNR_ACQUISITION_SCHEDULER_DISABLED` (`acquisition_scheduler.py:154`), `RUNR_SKIP_PROJECT_DOTENV` (`job_seeker.py:261`) and `RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT` (`bootstrap.py:324`), none of which touch auth.

### Recovery

- Revoke a Clerk session or user in Clerk. Cached contexts live at most 60 s (`_AUTH_CONTEXT_CACHE_TTL_SECONDS`). `_clear_auth_context_cache` exists (L7792) but has no HTTP trigger.
- Revoke an extension session with `revoke_current`, or let it expire (8 h).
- Rotate `CLERK_WEBHOOK_SECRET` / `SCRAPEOPS_API_KEY` in the provider dashboards and the Render env (`sync: false`). No in-app rotation tooling exists.
- Legacy tokens: `revoke_api_token` exists in the application, but its HTTP route is unregistered (C7). Revoking needs DB/CLI access.

## 7. Relevant tests and safe verification commands

| Test | Covers |
|---|---|
| `tests/test_log_privacy.py` | recursive redaction (L36), CLI/run summary (L56), worker formatter (L106), SQLite document normalization (L124) |
| `tests/test_career_url_discovery_security.py` | authenticated non-admin → 403, discovery not called (L69). Unauthenticated → 401/403 (L81). **Authz only; no SSRF URL-guard tests.** |
| `tests/test_scrapeops_integration.py` | proxy params (L26), envelope credits (L38), usage record (L56), health states (L76–135), retry behaviour (L147–223) |
| `tests/test_backend_api.py` | bearer required (L484); Clerk JWT no legacy fallback (L490); JWT plan (L507); auth cache (L533); CORS loopback/Render host/reject (L556/566/579); extension CORS exact (L592); originless extension header (L621); extension origin config (L634); Clerk-only identity + azp (L647); extension exchange one-time/origin-bound/revocable (L680); account delete (L2719); Clerk fallback identity hidden (L2895) |
| `tests/test_assisted_apply_connection_service.py`, `tests/test_assisted_apply_document_grants.py`, `tests/test_assisted_apply_package_routes.py` | extension connection and grant tokens (WS-9 primary) |
| `tests/test_env_config.py` | env schema validation |
| `tests/test_customer_route_surface.py` | removed admin surfaces not registered (L4) |
| `tests/test_phase_c_feed_performance_security.py` | cross-user isolation on feed (L26) |
| `tests/test_creem_integration.py`, `tests/test_phase_h_runr_pro.py` | see billing doc |

No test was found for: `clerk.verify_session_token` against a real RS256 key with issuer mismatch or unconfigured issuer; the manual Svix fallback; `secrets.resolve_secret_references`; `_is_public_https_url`.

Safe verification commands (**not executed in Phase 2**; a venv is needed, no network):

```bash
python -m pytest tests/test_log_privacy.py tests/test_career_url_discovery_security.py tests/test_scrapeops_integration.py -q
python -m pytest tests/test_backend_api.py -q -k "auth or clerk or cors or extension or origin or account_delete"
python -m pytest tests/test_assisted_apply_connection_service.py tests/test_env_config.py tests/test_customer_route_surface.py -q
git grep -n "auth_required=False" 58a96674 -- backend/api/routes
```

## 8. Historical decisions and supporting commits

`git log --oneline 58a96674 -- backend/integrations backend/security` plus pickaxe searches:

| SHA | Subject | Relevance |
|---|---|---|
| `334bb9b0` | Clerk IAM, MoR, Subscribtions | Clerk identity plus role/plan metadata introduced |
| `aae3028f` | Linux Production Setup + Clerk's JWT | JWT template / JWKS verification |
| `ec49b716` | ScrapeOps use AM control mechanisms and endpoint. | ScrapeOps integration and credit policy |
| `c7bf7cbd` | deoployment prep initial setup | env names / deployment wiring |
| `75bfdbc1` | Add Runr Assisted Apply connection foundation | PKCE extension connection, `_require_clerk_identity`, exact extension origins |
| `6d0ee461` | Enable Render PR previews | preview frontend host origin handling |
| `5a91380e` | reconstruct Phase I offline rollout evidence and disable career discovery API | career discovery API → 403 |
| `d6018c3e` | production busg resolution for render turso r2 | `RedactingFilter` introduced |
| `917e2588` | fix: implement bounded loading, retries, telemetry, and frontend resilience | ScrapeOps bounded retry |
| `7d382067` | Store career inventory as JSONL, dedupe, tracker | touches integrations |
| `b270d2cb` | recover acquisition audit permissions | acquisition permissions / audit |
| `e7662c63` | chore(scrapers): preserve verified pre-optimization baseline | latest change to owned paths |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Clerk JWT verification (RS256, JWKS, exp/nbf, issuer match when configured) | VERIFIED (scope: static. Code path `clerk.py:314–382` is reached from `server.py:7660` via `_auth_context` L9098 on all `auth_required=True` routes. Tests exist at `test_backend_api.py:490–647`, not executed.) |
| Clerk `azp` enforcement | PARTIAL (only in `_require_clerk_identity`, `server.py:9114–9123`; not in general auth) |
| Auth context cache (60 s) | IMPLEMENTED-UNVERIFIED |
| Legacy `bkat_` API token auth | VERIFIED (scope: static. `_build_legacy_auth_context` is reachable from `_resolve_auth_context` L7892.) Token **issuance/revocation over HTTP**: RETIRED/HISTORICAL (handlers unregistered, C7). |
| Role→scope authorization / admin guard | IMPLEMENTED-UNVERIFIED |
| Clerk webhook (Svix) user sync | VERIFIED (scope: static. Route `admin.webhooks.clerk` is registered at `admin.py:29` and the handler reaches `verify_clerk_webhook` → `_handle_clerk_webhook_event`.) |
| Self-service account deletion (deactivate + cancel local subscriptions) | VERIFIED (scope: static. `admin.account.delete` is registered at `admin.py:33` with the handler at L454.) Clerk-side deletion: not implemented in the handler. |
| Assisted Apply PKCE connection / origin-bound sessions | IMPLEMENTED-UNVERIFIED (service read; routes owned by WS-9) |
| CORS/origin policy incl. exact extension origins | VERIFIED (scope: static. `_enforce_origin_policy` is called in `do_GET`/`do_PUT` L9196/L9271 and in non-webhook `do_POST` L9234; production validation at `env_schema.py:410–433`.) |
| Log redaction (worker, CLI diagnostics, acquisition audit) | IMPLEMENTED-UNVERIFIED |
| Log redaction for API-process logs | UNKNOWN (WS6-G5) |
| Secret reference resolution | IMPLEMENTED-UNVERIFIED |
| Encrypted at-rest storage for `stored`-provider secrets | UNKNOWN (no encryption found in owned code and no ticket/doc plans it; T08 covers local data vaulting, not app secrets) |
| Career-URL discovery API disabled | VERIFIED (scope: static. Registered `workspace.py:33`; handler raises at L382; test L69.) |
| Connector public-HTTPS SSRF guard | PARTIAL (literal-IP/localhost checks only, no DNS resolution; WS6-G8) |
| ScrapeOps proxy / health / retry / usage API | IMPLEMENTED-UNVERIFIED (consumers: `services.py:71`, `company_enrichment.py:20`, `company_career_sites.py:27`, `job_boards/strategies.py:106–111`, `scripts/linkedin_company_enrichment_pipeline.py:1051`, …) |
| `GET /scrapeops/usage` customer usage | VERIFIED (scope: static. Prefix `admin.scrapeops` is registered at `admin.py:27`; branch L82 calls `get_scrapeops_user_usage_summary` `services.py:1672` and `get_scrapeops_usage_summary` L1534.) |
| Clerk user migration script | IMPLEMENTED-UNVERIFIED (`backend/scripts/migrate_users_to_clerk.py`) |

### Deployment evidence (documentary only)

- `render.yaml` (baseline file, not live state) declares `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_WEBHOOK_SECRET` (L126–131), `SCRAPEOPS_API_KEY` (L150 api, L239 worker) and `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` (L100–101) with `sync: false`, and sets `BACKEND_ALLOWED_ORIGINS` to two HTTPS frontend origins (L98–99).
- LAST-RECORDED production: Render `5dfdd106` per `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md`. Whether Clerk/ScrapeOps secrets are set on any live service is **UNKNOWN**. Live production = UNKNOWN (U1).

## 10. Confirmed gaps and unresolved questions

| ID | Gap / question |
|---|---|
| WS6-G1 | The legacy opaque-token fallback ("Clerk migration window", `server.py:7893`) has no sunset flag or date, and tokens can no longer be issued or revoked over HTTP (C7). Decide whether to remove the fallback or restore admin tooling. |
| WS6-G2 | `CLERK_ISSUER` is read (`clerk.py:202`) but is absent from `env_schema.py` and `render.yaml`. If both it and `CLERK_PUBLISHABLE_KEY` are unset, `verify_session_token` trusts the token's own `iss` to locate JWKS (`clerk.py:336–344`), which fails open. Confirm whether startup validation enforces schema `required: True` (not seen in `get_environment_validation_errors`). |
| WS6-G3 | `azp` is not checked in the default Clerk path (`server.py:7660`), and a token without `exp` is accepted (`clerk.py:360–362`). |
| WS6-G4 | Loopback origins are CORS-allowed in production (`server.py:8732`). |
| WS6-G5 | `RedactingFilter` is installed only by `configure_worker_logging`. Whether API-process logs (e.g. the legacy-fallback warning containing the exception text, `server.py:7877–7881`) are redacted is UNKNOWN. 500 responses echo `str(exc)` (`server.py:9224`). |
| WS6-G6 | `build_token_scope_set` merges arbitrary explicit scopes regardless of role (`auth.py:143–146`). `token_is_expired` treats an unparseable expiry as non-expiring (L176–178). |
| WS6-G7 | `SECRET_PROVIDER_STORED` values are stored and returned in plain form by `secrets.py:37–40`. No encryption layer found in owned code. |
| WS6-G8 | `_is_public_https_url` lacks DNS-resolution / redirect re-validation (`company_career_sites.py:517–535`). No unit test for the guard. |
| WS6-G9 | ScrapeOps retry returns early for all statuses below 500 (`scrapeops.py:567`), so 408/429 are never retried despite `_RETRYABLE_SCRAPEOPS_STATUSES`. The exhausted path returns `response=None` even when a 5xx response existed (L621,638). |
| WS6-G10 | `RUNR_DISABLE_QUOTAS` has no production guard (`env_schema.py:380–435`). `RUNR_PRIVATE_TEST_DEPLOYMENT` effect on auth not traced. |
| WS6-G11 | The ScrapeOps health probe targets a third-party echo service (`httpbin.org`) and spends a billed credit per probe (L22, L353–356). |
| C7 | Admin token/secret/user handler residue in `admin.py` (WS-11/WS-1). |
| U7 | Whether ScrapeOps usage events (`stage_adapters.py:141–165`) fall under "no analytics on Render" (owner decision). |
| U1 | Live revision unknown; no live auth verification performed. |
| T08 | **Security-adjacent open ticket:** encrypted owner-held vault plus off-machine copies for sensitive local ignored data (candidate assets, backend storage, generated documents). WS-5 owns it; WS-6 does the security review. Status ACTIVE. |
| T10 | **Security-adjacent open ticket:** privacy review of three customer personal branches on the hosted remote (branch names and contents intentionally not reproduced). WS-11/owner owns it; WS-6 gives security advice. Status ACTIVE. Includes re-running a credential scan before any retention decision. |

## Agent context and remaining work

### (a) Proposed agent context packet

- **Required reading:** this doc; [../05-subsystems/billing-and-creem.md](../05-subsystems/billing-and-creem.md); [backend-api.md](backend-api.md) (WS-1 routing); [../05-subsystems/assisted-apply.md](../05-subsystems/assisted-apply.md) (WS-9); [../../security/runr_data_ownership.md](../../security/runr_data_ownership.md); `backend/config/env_schema.py`; `server.py` L7640–7903 and L8721–8763, L9091–9147.
- **Allowed paths:** `backend/integrations/**`, `backend/security/**`, plus their tests. Changes in `backend/api/server.py` auth/CORS helpers need WS-1 coordination.
- **Tests to run:** `tests/test_log_privacy.py`, `tests/test_career_url_discovery_security.py`, `tests/test_scrapeops_integration.py`, `tests/test_creem_integration.py`, `tests/test_phase_h_runr_pro.py`, `tests/test_backend_api.py -k "auth or clerk or cors or extension or origin"`, `tests/test_assisted_apply_connection_service.py`, `tests/test_env_config.py`, `tests/test_customer_route_surface.py`.
- **Prohibited:** committing or logging secret values, webhook secrets, product IDs or host identifiers; weakening signature checks, origin allowlists or PKCE; re-registering retired admin routes; live Clerk/Creem/ScrapeOps calls or credit spend in tests; copying personal data (T10).

### (b) Registry proposal

| subsystem id | name | owned globs | primary doc | test globs | owner WS |
|---|---|---|---|---|---|
| `security-auth-integrations` | Integrations, authentication/security and billing | `backend/integrations/**`, `backend/security/**` | `docs/reverse-engineering/01-architecture/security-and-auth.md` | `tests/test_creem_integration.py`, `tests/test_scrapeops_integration.py`, `tests/test_phase_h_runr_pro.py`, `tests/test_log_privacy.py`, `tests/test_career_url_discovery_security.py` | WS-6 |

### (c) Gap / ticket candidates

1. Enforce the configured Clerk issuer (fail closed when unset), add `CLERK_ISSUER` to `env_schema.py`, and require `exp` plus `azp` allowlist in the default path (WS6-G2, G3).
2. Sunset the legacy API-token fallback or restore audited token management (WS6-G1, C7).
3. Add DNS-resolution SSRF checks and unit tests for `_is_public_https_url` (WS6-G8).
4. Confirm or install redaction on API logs; stop echoing exception text in 500s (WS6-G5).
5. Production guard for `RUNR_DISABLE_QUOTAS`; drop the loopback CORS allowance in production (WS6-G4, G10).
6. Fix the ScrapeOps retry early return for 408/429 (WS6-G9).
7. Encrypt stored secrets or restrict to the `env` provider (WS6-G7).
8. Track T08 and T10 to closure (security review inputs from WS-6).
