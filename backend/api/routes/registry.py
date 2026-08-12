from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol


class ApiHandler(Protocol):
    def _send_json(self, payload, status: int = 200, *, headers: dict[str, str] | None = None) -> None: ...

    def _send_html(self, body: str, status: int = 200, *, headers: dict[str, str] | None = None) -> None: ...

    def _send_no_content(
        self,
        status: int = 204,
        *,
        headers: dict[str, str] | None = None,
    ) -> None: ...

    def _send_error(
        self,
        status: int,
        code: str,
        message: str,
        *,
        details=None,
        headers: dict[str, str] | None = None,
    ) -> None: ...

    def _send_file(self, file_path: str, *, download_name: str = "") -> None: ...

    def _send_bytes(self, body: bytes, *, content_type: str, download_name: str) -> None: ...

    def _read_raw_body(self) -> bytes: ...

    def _read_json_body(self): ...

    def _require_identity(self): ...

    def _require_clerk_identity(self): ...

    def _require_scope(self, required_scope: str): ...

    def _require_acquisition_permission(self, permission: str): ...

    def _require_admin(self): ...

    def _require_workspace_access(self, *, workspace_id: str, required_scope: str): ...

    def _require_run_access(self, *, run, required_scope: str): ...

    def _request_origin(self) -> str: ...

    def _request_client_origin(self) -> str: ...

    def _bearer_token(self) -> str: ...

    def _request_api_prefix(self) -> str: ...


@dataclass(frozen=True)
class ApiRouteContext:
    application: Any
    handler: ApiHandler
    method: str
    segments: tuple[str, ...]
    query: Mapping[str, list[str]]

    def send_json(self, payload, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
        self.handler._send_json(payload, status=status, headers=headers)

    def send_html(self, body: str, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
        self.handler._send_html(body, status=status, headers=headers)

    def send_no_content(
        self,
        status: int = 204,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.handler._send_no_content(status=status, headers=headers)

    def send_error(
        self,
        status: int,
        code: str,
        message: str,
        *,
        details=None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.handler._send_error(status, code, message, details=details, headers=headers)

    def send_file(self, file_path: str, *, download_name: str = "") -> None:
        self.handler._send_file(file_path, download_name=download_name)

    def send_bytes(self, body: bytes, *, content_type: str, download_name: str) -> None:
        self.handler._send_bytes(body, content_type=content_type, download_name=download_name)

    def read_raw_body(self) -> bytes:
        return self.handler._read_raw_body()

    def read_json_body(self):
        return self.handler._read_json_body()

    def require_identity(self):
        return self.handler._require_identity()

    def require_clerk_identity(self):
        return self.handler._require_clerk_identity()

    def require_scope(self, required_scope: str):
        return self.handler._require_scope(required_scope)

    def require_acquisition_permission(self, permission: str):
        checker = getattr(self.handler, "_require_acquisition_permission", None)
        if callable(checker):
            return checker(permission)
        cached = getattr(self.handler, "_legacy_acquisition_admin_context", None)
        if cached is None:
            cached = self.handler._require_admin()
            setattr(self.handler, "_legacy_acquisition_admin_context", cached)
        return cached

    def require_admin(self):
        return self.handler._require_admin()

    def require_workspace_access(self, *, workspace_id: str, required_scope: str):
        return self.handler._require_workspace_access(workspace_id=workspace_id, required_scope=required_scope)

    def request_origin(self) -> str:
        return self.handler._request_origin()

    def request_client_origin(self) -> str:
        return self.handler._request_client_origin()

    def bearer_token(self) -> str:
        return self.handler._bearer_token()

    def request_api_prefix(self) -> str:
        return self.handler._request_api_prefix()


RouteHandler = Callable[[ApiRouteContext], bool | None]
RouteMatcher = Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True)
class ApiRoute:
    method: str
    name: str
    handler: RouteHandler
    auth_required: bool
    matcher: RouteMatcher

    def matches(self, method: str, segments: tuple[str, ...]) -> bool:
        return self.method == method.upper() and self.matcher(segments)


class RouteRegistry:
    def __init__(self) -> None:
        self._routes: list[ApiRoute] = []

    def register(self, route: ApiRoute) -> None:
        self._routes.append(route)

    def exact(
        self,
        method: str,
        segments: tuple[str, ...] | list[str],
        handler: RouteHandler,
        *,
        auth_required: bool = True,
        name: str = "",
    ) -> None:
        expected_segments = tuple(segments)
        self.register(
            ApiRoute(
                method=method.upper(),
                name=name or f"{method.upper()} {'/'.join(expected_segments)}",
                handler=handler,
                auth_required=auth_required,
                matcher=lambda request_segments: request_segments == expected_segments,
            )
        )

    def prefix(
        self,
        method: str,
        prefix: tuple[str, ...] | list[str],
        handler: RouteHandler,
        *,
        auth_required: bool = True,
        name: str = "",
    ) -> None:
        expected_prefix = tuple(prefix)

        def matches(request_segments: tuple[str, ...]) -> bool:
            if len(request_segments) < len(expected_prefix):
                return False
            for expected, actual in zip(expected_prefix, request_segments):
                if expected.startswith("{") and expected.endswith("}"):
                    if not actual:
                        return False
                    continue
                if actual != expected:
                    return False
            return True

        self.register(
            ApiRoute(
                method=method.upper(),
                name=name or f"{method.upper()} {'/'.join(expected_prefix)}/*",
                handler=handler,
                auth_required=auth_required,
                matcher=matches,
            )
        )

    def dispatch(self, context: ApiRouteContext, *, auth_required: bool) -> bool:
        for route in self._routes:
            if route.auth_required != auth_required:
                continue
            if not route.matches(context.method, context.segments):
                continue
            setattr(context.handler, "_matched_route_name", route.name)
            handled = route.handler(context)
            if handled is False:
                continue
            return True
        return False
