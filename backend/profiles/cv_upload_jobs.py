from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from backend.domain.models import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RunRecord,
    utc_now_iso,
)
from backend.domain.phase0_contracts import normalize_candidate_asset_descriptor
from backend.profiles.cv_profile_extraction import extract_cv_profile
from backend.profiles.document_text import create_word_companion_bytes, extract_document_text, extraction_metadata
from backend.repositories.contracts import BackendRepositories
from backend.storage import build_private_object_key


CV_UPLOAD_JOB_TYPE = "cv_upload_processing"
CV_UPLOAD_SYSTEM_WORKSPACE_ID = "__cv_upload__"
CV_UPLOAD_SYSTEM_WORKFLOW_ID = "__cv_upload__"

CV_STATUS_UPLOADED = "uploaded"
CV_STATUS_QUEUED = "queued"
CV_STATUS_PROCESSING = "processing"
CV_STATUS_READY = "ready"
CV_STATUS_FAILED = "failed"
CV_TERMINAL_STATUSES = {CV_STATUS_READY, CV_STATUS_FAILED}


def is_cv_upload_processing_run(run: RunRecord) -> bool:
    return str((run.metadata or {}).get("job_type") or "").strip() == CV_UPLOAD_JOB_TYPE


def cv_upload_status_url(job_id: str) -> str:
    return f"/cv-upload/{str(job_id or '').strip()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_assets(user) -> list[dict[str, Any]]:
    assets = []
    for asset in (user.metadata or {}).get("candidate_assets") or []:
        if isinstance(asset, Mapping):
            assets.append(normalize_candidate_asset_descriptor(asset))
    return assets


def _find_asset(assets: list[dict[str, Any]], asset_id: str) -> dict[str, Any]:
    target_asset_id = str(asset_id or "").strip()
    for asset in assets:
        if str(asset.get("asset_id") or "").strip() == target_asset_id:
            return asset
    raise KeyError(f"Candidate asset '{target_asset_id}' not found.")


def _persist_assets(repositories: BackendRepositories, user, assets: list[dict[str, Any]]):
    metadata = dict(user.metadata or {})
    metadata["candidate_assets"] = [normalize_candidate_asset_descriptor(asset) for asset in assets]
    user.metadata = metadata
    user.updated_at = _now()
    repositories.auth_repository.upsert_user(user)
    return repositories.auth_repository.get_user(user.user_id)


def update_cv_asset_processing_state(
    repositories: BackendRepositories,
    *,
    user_id: str,
    asset_id: str,
    status: str,
    job_id: str = "",
    error: str = "",
    extra_metadata: Mapping[str, Any] | None = None,
):
    user = repositories.auth_repository.get_user(user_id)
    assets = _load_assets(user)
    asset = _find_asset(assets, asset_id)
    metadata = dict(asset.get("metadata") or {})
    processing = dict(metadata.get("cv_processing") or {})
    now = _now()
    processing.update(
        {
            "status": status,
            "job_id": job_id or str(processing.get("job_id") or ""),
            "updated_at": now,
            "error": error,
        }
    )
    if status == CV_STATUS_QUEUED and not processing.get("queued_at"):
        processing["queued_at"] = now
    if status == CV_STATUS_PROCESSING:
        processing["started_at"] = now
    if status in CV_TERMINAL_STATUSES:
        processing["finished_at"] = now
    metadata.update(dict(extra_metadata or {}))
    metadata["status"] = status
    metadata["cv_processing"] = processing
    asset["metadata"] = metadata
    refreshed_user = _persist_assets(repositories, user, assets)
    return refreshed_user, _find_asset(_load_assets(refreshed_user), asset_id)


def enqueue_cv_upload_processing_run(
    repositories: BackendRepositories,
    *,
    user_id: str,
    asset_id: str,
    max_attempts: int = 3,
) -> tuple[RunRecord, dict[str, Any]]:
    user = repositories.auth_repository.get_user(user_id)
    asset = _find_asset(_load_assets(user), asset_id)
    metadata = dict(asset.get("metadata") or {})
    current_status = str(metadata.get("status") or CV_STATUS_READY).strip() or CV_STATUS_READY
    processing = dict(metadata.get("cv_processing") or {})
    existing_job_id = str(processing.get("job_id") or "").strip()
    if current_status in {CV_STATUS_UPLOADED, CV_STATUS_QUEUED, CV_STATUS_PROCESSING} and existing_job_id:
        try:
            return repositories.run_repository.get(existing_job_id), asset
        except KeyError:
            pass

    run = RunRecord.create(
        workspace_id=CV_UPLOAD_SYSTEM_WORKSPACE_ID,
        workflow_template_id=CV_UPLOAD_SYSTEM_WORKFLOW_ID,
        requested_by=f"api:{user_id}",
        max_attempts=max_attempts,
        metadata={
            "job_type": CV_UPLOAD_JOB_TYPE,
            "asset_id": asset_id,
            "user_id": user_id,
        },
    )
    now = utc_now_iso()
    run.status = RUN_STATUS_QUEUED
    run.queued_at = now
    run.updated_at = now
    repositories.run_repository.save(run)

    if current_status == CV_STATUS_READY and str(metadata.get("source_text") or "").strip():
        return run, asset
    _user, queued_asset = update_cv_asset_processing_state(
        repositories,
        user_id=user_id,
        asset_id=asset_id,
        status=CV_STATUS_QUEUED,
        job_id=run.id,
    )
    return run, queued_asset


def cv_upload_status_payload(
    repositories: BackendRepositories,
    *,
    user_id: str,
    job_id: str,
) -> dict[str, Any]:
    run = repositories.run_repository.get(job_id)
    if run.normalized_user_id != user_id and str((run.metadata or {}).get("user_id") or "") != user_id:
        raise PermissionError("CV upload job access denied.")
    asset_id = str((run.metadata or {}).get("asset_id") or "").strip()
    user = repositories.auth_repository.get_user(user_id)
    asset = _find_asset(_load_assets(user), asset_id)
    metadata = dict(asset.get("metadata") or {})
    processing = dict(metadata.get("cv_processing") or {})
    status = str(metadata.get("status") or processing.get("status") or "").strip()
    if not status:
        status = CV_STATUS_READY if str(metadata.get("source_text") or "").strip() else CV_STATUS_UPLOADED
    if run.status == RUN_STATUS_RUNNING and status not in CV_TERMINAL_STATUSES:
        status = CV_STATUS_PROCESSING
    if run.status == RUN_STATUS_QUEUED and status not in CV_TERMINAL_STATUSES:
        status = CV_STATUS_QUEUED
    if run.status == RUN_STATUS_FAILED and status != CV_STATUS_READY:
        status = CV_STATUS_FAILED
    parsed_profile = dict(metadata.get("parsed_profile") or {})
    source_text = str(metadata.get("source_text") or "")
    extraction = dict(metadata.get("profile_extraction") or {})
    return {
        "asset_id": asset_id,
        "job_id": run.id,
        "status": status,
        "status_url": cv_upload_status_url(run.id),
        "asset": asset,
        "parsed": parsed_profile,
        "cv_text": source_text if status == CV_STATUS_READY else "",
        "char_count": len(source_text) if status == CV_STATUS_READY else 0,
        "extraction": extraction,
        "error": str(processing.get("error") or run.last_error or ""),
        "run": run.to_dict(),
    }


def _asset_file_payload(asset: Mapping[str, Any]) -> dict[str, Any]:
    return dict(asset.get("file") or {})


def _asset_object_key(asset: Mapping[str, Any]) -> str:
    file_payload = _asset_file_payload(asset)
    return str(file_payload.get("object_key") or asset.get("object_key") or "").strip()


def _asset_filename(asset: Mapping[str, Any]) -> str:
    display_name = str(asset.get("display_name") or "").strip()
    if display_name:
        return display_name
    file_payload = _asset_file_payload(asset)
    return Path(str(file_payload.get("path") or "")).name or str(asset.get("asset_id") or "cv-upload")


def _store_word_companion_if_needed(
    *,
    object_storage: Any,
    user_id: str,
    asset: Mapping[str, Any],
    cv_text: str,
) -> dict[str, str]:
    metadata = dict(asset.get("metadata") or {})
    if str(metadata.get("word_companion_object_key") or "").strip():
        return {}
    file_payload = _asset_file_payload(asset)
    extension = str(file_payload.get("extension") or Path(_asset_filename(asset)).suffix.lower().lstrip(".")).lower()
    if extension == "docx":
        return {}
    asset_id = str(asset.get("asset_id") or "").strip()
    companion_name = f"{Path(_asset_filename(asset)).stem or asset_id}.docx"
    companion_key = build_private_object_key(
        namespace="users",
        owner_id=user_id,
        category=str(asset.get("asset_kind") or "workspace_cv"),
        object_id=f"{asset_id}-word-companion",
        filename=companion_name,
    )
    object_storage.put(
        companion_key,
        create_word_companion_bytes(cv_text, title=_asset_filename(asset)),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        metadata={"user_id": str(user_id), "asset_id": asset_id},
    )
    return {
        "word_companion_path": "",
        "word_companion_object_key": companion_key,
        "word_companion_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }


def _complete_run(repositories: BackendRepositories, run: RunRecord) -> RunRecord:
    now = utc_now_iso()
    run.status = RUN_STATUS_COMPLETED
    run.finished_at = now
    run.updated_at = now
    run.current_stage_id = ""
    run.last_error = ""
    repositories.run_repository.save(run)
    return repositories.run_repository.get(run.id)


def _fail_or_retry_run(
    repositories: BackendRepositories,
    run: RunRecord,
    *,
    error: str,
    auto_retry_failed: bool,
) -> RunRecord:
    now = utc_now_iso()
    run.status = RUN_STATUS_FAILED
    run.finished_at = now
    run.updated_at = now
    run.current_stage_id = ""
    run.last_error = error
    repositories.run_repository.save(run)
    if auto_retry_failed and run.attempt_count < run.max_attempts:
        run.status = RUN_STATUS_QUEUED
        run.queued_at = utc_now_iso()
        run.started_at = ""
        run.finished_at = ""
        run.updated_at = run.queued_at
        repositories.run_repository.save(run)
    return repositories.run_repository.get(run.id)


def process_cv_upload_run(
    *,
    repositories: BackendRepositories,
    object_storage: Any,
    run: RunRecord,
    auto_retry_failed: bool = True,
    logger: logging.Logger | None = None,
) -> RunRecord:
    log = logger or logging.getLogger("backend.worker.cv_upload")
    user_id = str((run.metadata or {}).get("user_id") or run.normalized_user_id).strip()
    asset_id = str((run.metadata or {}).get("asset_id") or "").strip()
    try:
        user = repositories.auth_repository.get_user(user_id)
        assets = _load_assets(user)
        asset = _find_asset(assets, asset_id)
        metadata = dict(asset.get("metadata") or {})
        if str(metadata.get("status") or "") == CV_STATUS_READY and str(metadata.get("source_text") or "").strip():
            return _complete_run(repositories, run)

        update_cv_asset_processing_state(
            repositories,
            user_id=user_id,
            asset_id=asset_id,
            status=CV_STATUS_PROCESSING,
            job_id=run.id,
            extra_metadata={"processing_started_at": _now()},
        )
        user = repositories.auth_repository.get_user(user_id)
        asset = _find_asset(_load_assets(user), asset_id)
        object_key = _asset_object_key(asset)
        if not object_key:
            raise ValueError(f"CV asset '{asset_id}' is missing its source object key.")
        source_bytes = object_storage.get(object_key)
        document_extraction = extract_document_text(_asset_filename(asset), source_bytes, allow_ocr=False)
        cv_text = str(document_extraction.get("text") or "").strip()
        if not cv_text:
            warning = " ".join(str(item) for item in document_extraction.get("warnings") or []).strip()
            detail = f" {warning}" if warning else ""
            raise ValueError(f"Could not extract any text from uploaded file '{_asset_filename(asset)}'.{detail}")

        extraction = extract_cv_profile(cv_text)
        companion_metadata = _store_word_companion_if_needed(
            object_storage=object_storage,
            user_id=user_id,
            asset=asset,
            cv_text=cv_text,
        )
        extra_metadata = {
            **extraction_metadata(document_extraction),
            **companion_metadata,
            "content_sha256": str(metadata.get("content_sha256") or sha256(source_bytes).hexdigest()),
            "parsed_profile": dict(extraction.get("profile") or {}),
            "profile_extraction": {
                "provider": str(extraction.get("provider") or ""),
                "model": str(extraction.get("model") or ""),
                "warnings": list(extraction.get("warnings") or []),
                "extracted_at": str(extraction.get("extracted_at") or ""),
            },
            "processed_at": _now(),
        }
        refreshed_user, _asset = update_cv_asset_processing_state(
            repositories,
            user_id=user_id,
            asset_id=asset_id,
            status=CV_STATUS_READY,
            job_id=run.id,
            extra_metadata=extra_metadata,
        )
        user_metadata = dict(refreshed_user.metadata or {})
        user_metadata["cv_text"] = cv_text
        refreshed_user.metadata = user_metadata
        refreshed_user.updated_at = _now()
        repositories.auth_repository.upsert_user(refreshed_user)
        return _complete_run(repositories, run)
    except Exception as exc:
        message = str(exc)
        log.exception("cv_upload_processing_failed", extra={"run_id": run.id, "asset_id": asset_id, "user_id": user_id})
        try:
            update_cv_asset_processing_state(
                repositories,
                user_id=user_id,
                asset_id=asset_id,
                status=CV_STATUS_FAILED,
                job_id=run.id,
                error=message,
            )
            if auto_retry_failed and run.attempt_count < run.max_attempts:
                update_cv_asset_processing_state(
                    repositories,
                    user_id=user_id,
                    asset_id=asset_id,
                    status=CV_STATUS_QUEUED,
                    job_id=run.id,
                    error=message,
                )
        except Exception:
            log.exception("cv_upload_processing_state_update_failed", extra={"run_id": run.id, "asset_id": asset_id})
        return _fail_or_retry_run(
            repositories,
            run,
            error=message,
            auto_retry_failed=auto_retry_failed,
        )


def clone_asset_with_status(asset: Mapping[str, Any], status: str, *, job_id: str = "") -> dict[str, Any]:
    cloned = deepcopy(dict(asset))
    metadata = dict(cloned.get("metadata") or {})
    processing = dict(metadata.get("cv_processing") or {})
    processing.update({"status": status, "job_id": job_id or str(processing.get("job_id") or "")})
    metadata["status"] = status
    metadata["cv_processing"] = processing
    cloned["metadata"] = metadata
    return normalize_candidate_asset_descriptor(cloned)
