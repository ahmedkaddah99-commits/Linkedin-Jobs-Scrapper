> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Turso / libSQL and database connection selection

This is a secondary doc of the 03-data group; the group primary is [schema-and-migrations.md](schema-and-migrations.md) and the WS-5 subsystem primary is [domain-model.md](../01-architecture/domain-model.md). LIVE PRODUCTION = UNKNOWN. No Turso database was contacted. Env keys appear as names only.

## 1. Purpose and capabilities

One synchronous facade, `DatabaseConnection` (`backend/database/connection.py:316`), sits over either stdlib `sqlite3` (local development and tests) or the `libsql` Python driver (remote Turso). All repositories and the migration engine use it. A separate, optional MySQL sink exists only for a career-discovery tool.

## 2. Owned paths

`backend/database/connection.py` (589 lines), `backend/database/initialization.py`, `backend/repositories/sqlite_core.py` (91), `backend/repositories/mysql_career_discovery.py` (197), `backend/config/env_schema.py` (DB keys).

## 3. Entry points

| Entry point | Code | Invoked by |
|---|---|---|
| `connect_database(local_path)` | `connection.py:525` | `backend/repositories/sqlite_core.py` (every `_SqliteStore._connect`); `backend/acquisition/reprocessing.py` (WS-3) |
| `database_session(path)` | `connection.py:564` | `sqlite_core.py` transactions; `backend/database/initialization.py:46` (migration batch) |
| `database_target_info()` | `connection.py:507` | `backend/api/routes/system.py:45` (readiness route, WS-1); `backend/bootstrap.py:364` (test boundary) |
| `initialize_database(path, force)` | `backend/database/initialization.py:29` | `backend/bootstrap.py:286`; `sqlite_core.py:19`; `backend/database/migrate.py`; `backend/acquisition/reprocessing.py:152` |
| `validate_environment()` | `backend/config/env_schema.py:438` | `migrate.py:31`; `backend/api/server.py:85`; `backend/storage/factory.py:18` |
| `MySqlCareerDiscoveryStore` | `mysql_career_discovery.py:71` | only `backend/tools/discover_company_careers.py:20-22,897` |

## 4. Selection matrix

| Condition (evaluated per connection) | Engine | Code |
|---|---|---|
| `TURSO_DATABASE_URL` non-empty | libSQL remote | `connection.py:484-485`, `528-529` |
| URL empty **and** (`DATABASE_BACKEND=turso` **or** `RUNR_ENV` ∈ {prod, production}) | error `DatabaseConfigurationError` ("TURSO_DATABASE_URL is required…") | `connection.py:496-497`, `530-533` |
| libSQL selected, `TURSO_AUTH_TOKEN` empty | error | `connection.py:534-538` |
| libSQL selected, `libsql` not importable | error | `connection.py:539-544` |
| otherwise | `sqlite3.connect(path, timeout=30)`; parent dir created | `connection.py:553-556` |
| always | `PRAGMA foreign_keys = ON` | `connection.py:558` |

Consequences:
- **Setting `TURSO_DATABASE_URL` alone switches to remote, even with `DATABASE_BACKEND=sqlite`.** `validate_environment` does not flag this combination.
- The `--database`/`db_path` argument is ignored for libSQL. All processes then share one remote database.
- `RUNR_STORAGE_BACKEND=sqlite` (repository family, `deploy/start.sh:13`, `render.yaml` L94-95/L211-212) is a separate setting from `DATABASE_BACKEND` (engine). On Render both are set: `sqlite` family and `turso` engine.

Env key names:
- In `ENV_SCHEMA`: `RUNR_ENV`, `DATABASE_BACKEND`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.
- Related, outside the schema: `RUNR_STORAGE_BACKEND`, `RUNR_DATA_DIR`.
- MySQL sink (outside the schema): `CAREER_DISCOVERY_MYSQL_{HOST,PORT,USER,PASSWORD,DATABASE,TABLE}` with `MYSQL_*` fallbacks (`mysql_career_discovery.py:46-53`).

Validation (`backend/config/env_schema.py:375-435`): `DATABASE_BACKEND` ∈ {sqlite, turso}. Turso or production requires URL and token. Production requires `DATABASE_BACKEND=turso`.

`database_target_info()` (`connection.py:507-522`) returns backend, environment, target, `remote_required`, `remote_configured` and a URL **scheme prefix only**, never the URL. The readiness route uses it (`backend/api/routes/system.py:45`), as does the test boundary (`backend/bootstrap.py:364`).

## 5. Call and data flows

- **Retry** (`_retry_libsql_operation`, `connection.py:151-183`): up to 4 attempts. Backoff `min(2.0, 0.25·2^(n-1))` plus up to 0.1 s jitter, with a structured `database_operation_retry` warning log.
  - Transient markers: 502/503, "service unavailable", timeouts, connection reset/refused/aborted, broken pipe, network/transport, stream-not-found/"stream already in use" (L53-76). Also driver panics (`PanicException` from `pyo3_runtime`/`libsql`, L78-79, L135-145).
  - Never retried: auth/403/401/400, constraint, syntax, no such table/column, SQLITE_* codes (L23-51).
- **Reconnect** on `stale_stream`/`driver_panic` before retrying (`_refresh_connection_for_retry`, L331-340). History: `93419e48` "fix: recover occupied Turso streams".
- **Statement vs transaction.**
  - Outside a transaction, each `execute`/`executemany`/`commit` retries individually (`_run`, L342-349).
  - `transaction(callback)` (L351-383) disables per-statement retry and replays the **whole callback** on transient failure. Callbacks must therefore be idempotent or rely on the rolled-back state.
- **Rowcount.** libSQL cursors may report -1. For DML, `SELECT changes()` supplies the count (L385-397, `_statement_changes_rows` L309).
- **Sessions.**
  - `database_session` (L564-589) commits on success, rolls back on error, and cleanup errors never mask the primary error (`_handle_cleanup_failure` L196).
  - `_SqliteStore.transaction_scope` (`backend/repositories/sqlite_core.py:29-68`) shares one connection for bounded batches, to cut Turso round trips during producer delivery.
- **Initialization memo** (`backend/database/initialization.py:22-26`): remote targets use identity `"remote"`, so a process migrates Turso at most once unless `force=True`. The migration flow itself is in [schema-and-migrations.md §5](schema-and-migrations.md#5-call-and-data-flows).
- **Test isolation** (`backend/bootstrap.py:354-380`): test context refuses any remote configuration, `DATABASE_BACKEND=turso`, production env, and the default `.backend_data` path.

### Shared-database topology (documentary plus config)
Per `render.yaml`, the Render api and worker use the Turso engine. Per the handoff doc (documentary), the VPS publisher writes the **shared** Turso catalog. WS-7 covers topology in [vps-runtime-and-acquisition-timers.md](../02-deployment/vps-runtime-and-acquisition-timers.md); WS-3 covers the producer-local SQLite state DBs in [acquisition-source-state.md](acquisition-source-state.md). Those producer state DBs use plain SQLite files outside git and are not the libSQL path described here.

### MySQL career discovery (not part of the app DB)
`MySqlCareerDiscoveryStore` (`backend/repositories/mysql_career_discovery.py:71-197`) validates the table identifier (L17), lazily imports `pymysql`, creates its table and upserts discovery results. Its only caller is `backend/tools/discover_company_careers.py`. It is not used by bootstrap, Render or migrations.

## 6. Invariants, failure handling and recovery

- Every connection runs `PRAGMA foreign_keys = ON` (`connection.py:558`); migration batches and store writes roll back atomically on error (`database_session`, L564-589).
- Only classified-transient errors are retried; auth, constraint and syntax errors fail fast (L23-80). Cleanup failures never mask the primary error (L196).
- Production cannot run without Turso: `env_schema.py` production rule plus `connect_database` enforcement (`connection.py:496-497`, `530-533`).
- Test context refuses remote/production configuration outright (`backend/bootstrap.py:354-380`).
- Whole-transaction replay (L351-383) assumes caller callbacks are idempotent; not audited per store (WS5-T2).

## 7. Historical decisions and supporting commits

`git log --oneline 58a96674 -- backend/database/` is 9 commits; the connection-relevant ones:

| Commit | Date | Subject | Decision |
|---|---|---|---|
| `c7bf7cbd` | 2026-06-18 | deoployment prep initial setup | `connection.py` facade introduced (sqlite3/libsql split) |
| `10e65b01` | 2026-06-21 | Production Tech Stack Correction | Turso as production engine |
| `d6018c3e` | 2026-07 | production busg resolution for render turso r2 | libSQL fixes |
| `386ea700` | 2026-07-02 | Turso fix | further hardening |
| `93419e48` | 2026-08-04 | fix: recover occupied Turso streams | stale-stream reconnect + panic replay |

## 8. Tests and safe verification (not executed in Phase 2)

`tests/test_database_connection.py` (19 tests) covers:
- the libSQL env contract (L147)
- transient recovery (L185-309)
- panic replay (L348)
- non-retryable errors (L410)
- the token requirement (L430)
- the installed-driver adapter (L445)
- the turso-requires-URL rule (L475)

`tests/test_env_config.py` covers the production Turso rules (L115).

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_database_connection.py tests/test_env_config.py
```
Safe verification commands, not executed in Phase 2. Do not run anything with real `TURSO_*` values.

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Engine selection sqlite/libSQL | VERIFIED (scope: static read `connection.py:484-560`) |
| Transient retry/reconnect/transaction replay | IMPLEMENTED-UNVERIFIED (fake-driver tests only) |
| Production requires Turso | VERIFIED (scope: static `env_schema.py:420-422` rule, and `connect_database` enforcement) |
| MySQL career-discovery sink | IMPLEMENTED-UNVERIFIED (tool-only) |

### Deployment evidence (documentary only)
- `docs/deployment/render.md` L93-95 name `DATABASE_BACKEND=turso` and a `libsql://` URL placeholder.
- `render.yaml` marks `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` `sync: false`.
- The handoff doc (2026-09-11) and the untracked 2026-09-12 report describe the shared Turso publication catalog with counts.

Current state is UNKNOWN.

## 10. Confirmed gaps and unresolved questions

| ID | Item |
|---|---|
| WS5-T1 | `TURSO_DATABASE_URL` set with `DATABASE_BACKEND=sqlite` silently selects remote; validation does not warn |
| WS5-T2 | Whole-transaction replay assumes idempotent callbacks; not audited per store (WS-3/WS-4 transaction callers) |
| WS5-S1 | Startup auto-migration against shared Turso from any role (see [schema-and-migrations.md](schema-and-migrations.md)) |
| WS5-G5 | No real-Turso integration test (offline by design) |

## Agent context and remaining work

**(a) Agent context packet**
- Required reading: this doc; [schema-and-migrations.md](schema-and-migrations.md) (group primary); [domain-model.md](../01-architecture/domain-model.md); `backend/database/connection.py`; `backend/database/initialization.py`; `backend/repositories/sqlite_core.py`; `backend/config/env_schema.py:375-435`.
- Allowed paths: `backend/database/connection.py`, `backend/database/initialization.py`, `backend/repositories/sqlite_core.py`, `backend/repositories/mysql_career_discovery.py`.
- Tests to run: `.venv\Scripts\python.exe -m pytest -q tests/test_database_connection.py tests/test_env_config.py` (safe verification commands, not executed in Phase 2).
- Prohibited: using real `TURSO_*`/`MYSQL_*` credentials or contacting any database during documentation work; changing the transient/non-transient error classification without extending `tests/test_database_connection.py`; altering retry/transaction semantics without the fake-driver tests passing.

**(b) Registry proposal** (slice row; the WS-5 subsystem row is in [domain-model.md §Agent context](../01-architecture/domain-model.md#agent-context-and-remaining-work))

| id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `db-connection-turso` | Turso/libSQL connection layer | `backend/database/connection.py`, `backend/repositories/sqlite_core.py`, `backend/repositories/mysql_career_discovery.py` | `docs/reverse-engineering/03-data/turso-and-libsql.md` | `tests/test_database_connection.py`, `tests/test_env_config.py` | WS-5 |

**(c) Gap and ticket candidates**
1. Warn (or error) in `validate_environment` when `TURSO_DATABASE_URL` is set but `DATABASE_BACKEND=sqlite` (WS5-T1).
2. Audit transaction callbacks for idempotency under replay (WS5-T2; with WS-3/WS-4).
3. WS5-S1 startup-migration role decision (tracked in [schema-and-migrations.md](schema-and-migrations.md)).
