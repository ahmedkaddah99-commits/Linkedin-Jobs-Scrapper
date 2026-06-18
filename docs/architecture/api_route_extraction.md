# API Route Extraction Guide

Status: active agent context

Date: 2026-05-31

`backend/api/server.py` is still the compatibility host for the HTTP server, CORS, auth resolution, body parsing helpers, and shared route helper functions. Route bodies live in `backend/api/routes/` by domain.

## Current Foundation

- `backend/api/routes/registry.py` owns `RouteRegistry`, `ApiRoute`, and `ApiRouteContext`.
- `backend/api/routes/__init__.py` builds the registry and is the only place that wires domain route modules together.
- `backend/api/routes/system.py` owns public GET `/` and `/health`.
- `backend/api/routes/admin.py` owns admin, billing, settings, analytics, users, secrets, auth/me, and webhooks.
- `backend/api/routes/documents.py` owns documents, uploads, exports, CV preview, and ATS export gate.
- `backend/api/routes/tracker.py` owns tracker, referrals, Gmail/Google OAuth, outreach, rejected jobs, and people discovery.
- `backend/api/routes/workspace.py` owns workspaces, workspace builder, templates, runs, run resources, and workers.
- `build_handler()` creates one registry and the handler dispatches to it before returning a shared 404 response.
- `/v1` compatibility is handled before dispatch by `server.py`; route modules should register normalized segments without `v1`.

## Adding A Domain Route Module

1. Create a module such as `backend/api/routes/workspaces.py`.
2. Add `register_routes(registry: RouteRegistry) -> None`.
3. Register exact or prefix routes:

```python
def register_routes(registry: RouteRegistry) -> None:
    registry.exact("GET", ("workspaces",), list_workspaces, auth_required=True, name="workspaces.list")
    registry.prefix("GET", ("workspaces",), get_workspace_child, auth_required=True, name="workspaces.child")
```

4. Import and call that module's `register_routes()` from `backend/api/routes/__init__.py`.
5. Move any shared helper needed by multiple route modules only when there is a clear ownership boundary. Otherwise keep compatibility helpers in `server.py` until a later service-boundary extraction.
6. Run a focused API test for the moved route plus the auth/CORS smoke tests.

## Handler Rules

- Route handlers receive `ApiRouteContext`.
- Use `context.send_json()`, `context.send_html()`, `context.send_error()`, and `context.send_file()` instead of reaching into the HTTP handler directly.
- Use `context.require_identity()`, `context.require_scope()`, `context.require_admin()`, or `context.require_workspace_access()` for auth checks.
- Use `context.read_raw_body()` for multipart or webhook routes and `context.read_json_body()` for JSON routes.
- Prefix handlers may return `False` to decline and let later routes handle the request. Prefer declining before reading the body. JSON body reads are cached by the compatibility handler, but raw multipart/webhook handlers must not return `False` after consuming the stream.
- Otherwise, send a response and return `None` or `True`.

The first extraction wave kept copied route bodies close to their original shape and uses `route_support.bind_server_globals()` so tests and runtime patches that target `backend.api.server` continue to work. Prefer new helper methods on `ApiRouteContext` for new routes; reduce dynamic server helper binding only when extracting stable helpers into dedicated service modules.

## Public And Protected Phases

Each HTTP method dispatches public routes first with `auth_required=False`, then protected routes with `auth_required=True`, then returns the shared not-found response.

`auth_required=True` means the route is registered in the protected phase. It does not automatically authenticate the request. The route handler must still call the relevant `context.require_*()` helper so each endpoint keeps its existing scope and workspace checks.

Keep route modules domain-focused. A follow-up route extraction ticket should usually touch one existing `backend/api/routes/<domain>.py` module, `backend/api/routes/__init__.py` only if ownership changes, shared helpers only when necessary, and focused API tests.
