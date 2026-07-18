from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from backend.api.routes.assisted_apply import (
    _authenticate_extension_session,
    _read_strict_object,
)
from backend.api.routes.registry import ApiRouteContext, RouteRegistry

_CREATE_PACKAGE_KEYS = {"job", "answers", "documents", "warnings"}
_BIND_PACKAGE_KEYS = {"binding_id"}
_DOCUMENT_GRANT_KEYS = {"package_id", "document_id"}
_CORRECTION_KEYS = {"package_id", "field_intent", "corrected_value", "scope"}
_TELEMETRY_KEYS = {
    "schema_version", "adapter", "adapter_version", "lifecycle_stage",
    "aggregate_outcome", "error_category", "document_role",
}
_OUTCOME_KEYS = {
    "package_id", "package_version", "adapter", "adapter_version",
    "evidence_category", "decision", "uploaded_documents",
}


def register_routes(registry: RouteRegistry) -> None:
    # Web (Clerk-authenticated)
    registry.exact(
        "POST",
        ("assisted-apply", "packages"),
        _create_package,
        auth_required=True,
        name="assisted_apply.packages.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "packages", "launch"),
        _launch_package,
        auth_required=True,
        name="assisted_apply.packages.launch",
    )

    # Extension (session-authenticated)
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "packages", "bind"),
        _bind_package,
        auth_required=False,
        name="assisted_apply.extension.packages.bind",
    )
    registry.exact(
        "GET",
        ("assisted-apply", "extension", "packages"),
        _get_package_for_extension,
        auth_required=False,
        name="assisted_apply.extension.packages.get",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "document-grants"),
        _create_document_grant,
        auth_required=False,
        name="assisted_apply.extension.document_grants.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "document-grants", "download"),
        _download_document_grant,
        auth_required=False,
        name="assisted_apply.extension.document_grants.download",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "corrections"),
        _save_correction,
        auth_required=False,
        name="assisted_apply.extension.corrections.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "telemetry"),
        _record_upload_telemetry,
        auth_required=False,
        name="assisted_apply.extension.telemetry.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "application-outcomes"),
        _respond_to_application_outcome,
        auth_required=False,
        name="assisted_apply.extension.application_outcomes.create",
    )


def _create_package(context: ApiRouteContext) -> None:
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(
        context,
        allowed_keys=_CREATE_PACKAGE_KEYS,
        label="application package",
    )
    package = context.application.create_application_package(
        user_id=user.user_id,
        job=payload.get("job") or {},
        answers=payload.get("answers"),
        documents=payload.get("documents"),
        warnings_items=payload.get("warnings"),
    )
    context.send_json(package.to_extension_payload(), status=HTTPStatus.CREATED)


def _launch_package(context: ApiRouteContext) -> None:
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(
        context,
        allowed_keys={"package_id"},
        label="package launch",
    )
    package = context.application.launch_application_package(
        user_id=user.user_id,
        package_id=str(payload.get("package_id") or "").strip(),
    )
    context.send_json(
        {
            "package_id": package.package_id,
            "binding_id": package.launch_tab_binding_id,
            "binding_expires_at": package.launch_tab_binding_expires_at,
            "status": package.status,
        },
        status=HTTPStatus.OK,
    )


def _bind_package(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_BIND_PACKAGE_KEYS,
        label="package bind",
    )
    package = context.application.bind_application_package(
        binding_id=str(payload.get("binding_id") or "").strip(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(package.to_extension_payload(), status=HTTPStatus.OK)


def _get_package_for_extension(context: ApiRouteContext) -> None:
    user, _connection = _authenticate_extension_session(context)
    package_id = str(
        list(context.query.get("package_id") or [""])[0]
    ).strip()
    if not package_id:
        raise ValueError("package_id query parameter is required.")
    payload = context.application.get_application_package_for_extension(
        package_id=package_id,
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(payload, status=HTTPStatus.OK)


def _create_document_grant(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_DOCUMENT_GRANT_KEYS,
        label="document grant",
    )
    result = context.application.create_assisted_apply_document_grant(
        package_id=str(payload.get("package_id") or "").strip(),
        document_id=str(payload.get("document_id") or "").strip(),
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(result, status=HTTPStatus.CREATED)


def _download_document_grant(context: ApiRouteContext) -> None:
    _read_strict_object(context, allowed_keys=set(), label="document download")
    file_bytes, metadata = context.application.consume_assisted_apply_document_grant(
        raw_grant=str(context.handler.headers.get("X-Runr-Document-Grant") or "").strip(),
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_bytes(
        file_bytes,
        content_type=metadata["mimeType"],
        download_name=metadata["fileName"],
    )


def _save_correction(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_CORRECTION_KEYS,
        label="application correction",
    )
    result = context.application.save_assisted_apply_correction(
        package_id=str(payload.get("package_id") or "").strip(),
        field_intent=str(payload.get("field_intent") or "").strip(),
        corrected_value=str(payload.get("corrected_value") or "").strip(),
        scope=str(payload.get("scope") or "").strip(),
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(result, status=HTTPStatus.CREATED if result["persisted"] else HTTPStatus.OK)


def _record_upload_telemetry(context: ApiRouteContext) -> None:
    _authenticate_extension_session(context)
    payload = _read_strict_object(
        context,
        allowed_keys=_TELEMETRY_KEYS,
        label="adapter health telemetry",
    )
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported adapter health telemetry schema.")
    allowed = {
        "adapter": {"greenhouse", "lever"},
        "lifecycle_stage": {"upload"},
        "aggregate_outcome": {"accepted", "rejected", "mismatched", "preserved", "unsupported"},
        "error_category": {"none", "control_unavailable", "control_blocked", "mime_rejected", "portal_rejected", "existing_value", "unsupported_role", "unknown"},
        "document_role": {"cv", "cover_letter", "supporting_document"},
    }
    for key, values in allowed.items():
        if payload.get(key) not in values:
            raise ValueError(f"Invalid adapter health telemetry {key}.")
    adapter_version = str(payload.get("adapter_version") or "")
    if len(adapter_version) > 32 or not all(part.isdigit() for part in adapter_version.split(".")):
        raise ValueError("Invalid adapter health telemetry adapter_version.")
    logging.getLogger("backend.api.assisted_apply_telemetry").info(
        "assisted_apply_adapter_health",
        extra={f"telemetry_{key}": value for key, value in payload.items()},
    )
    context.send_json({"recorded": True}, status=HTTPStatus.ACCEPTED)


def _respond_to_application_outcome(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_OUTCOME_KEYS,
        label="application outcome",
    )
    raw_documents = payload.get("uploaded_documents") or []
    if not isinstance(raw_documents, list) or not all(
        isinstance(item, dict) and set(item) == {"document_id", "document_version"}
        for item in raw_documents
    ):
        raise ValueError("uploaded_documents must be an array of document references.")
    result = context.application.respond_to_assisted_apply_outcome(
        package_id=str(payload.get("package_id") or "").strip(),
        package_version=int(payload.get("package_version") or 0),
        adapter=str(payload.get("adapter") or "").strip(),
        adapter_version=str(payload.get("adapter_version") or "").strip(),
        evidence_category=str(payload.get("evidence_category") or "").strip(),
        decision=str(payload.get("decision") or "").strip(),
        uploaded_documents=raw_documents,
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(result, status=HTTPStatus.CREATED if result["created"] else HTTPStatus.OK)
