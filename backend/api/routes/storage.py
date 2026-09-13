# ruff: noqa: F821
from __future__ import annotations

import mimetypes
from http import HTTPStatus
from urllib.parse import unquote

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.api.routes.route_support import bind_server_globals
from backend.storage import ObjectNotFoundError, validate_object_download


_SERVER_BIND_RESERVED = {"register_routes", "_handle_get", "_bind_server_globals"}


def _bind_server_globals() -> None:
    bind_server_globals(globals())


def register_routes(registry: RouteRegistry) -> None:
    # Local storage is the only backend whose signed URL terminates at Runr.
    # S3/R2 links bypass the API entirely.
    registry.prefix("GET", ("storage", "objects"), _handle_get, auth_required=False, name="storage.objects")


def _handle_get(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    if len(context.segments) < 3:
        return False
    storage = context.application.object_storage
    verifier = getattr(storage, "verify_signed_download", None)
    if not callable(verifier):
        context.send_error(HTTPStatus.NOT_FOUND, "not_found", "Signed object route is unavailable.")
        return True

    key = "/".join(unquote(str(segment)) for segment in context.segments[2:])
    query = context.query
    expires = str((query.get("expires") or [""])[0])
    signature = str((query.get("signature") or [""])[0])
    download_name = str((query.get("download") or [""])[0])
    try:
        normalized_key = verifier(
            key,
            expires_at=expires,
            signature=signature,
            download_filename=download_name,
        )
        body = storage.get(normalized_key)
        filename = download_name or key.rsplit("/", 1)[-1] or "download"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        validate_object_download(content_type=content_type, size=len(body), filename=filename)
    except ObjectNotFoundError:
        context.send_error(HTTPStatus.NOT_FOUND, "not_found", "Signed object URL is expired or invalid.")
        return True

    context.handler._send_bytes(body, content_type=content_type, download_name=filename)
    return True
