# ruff: noqa: F821
from __future__ import annotations

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.api.routes.route_support import bind_server_globals

# Documents, uploads, exports, CV preview, and ATS export gate.
_SERVER_BIND_RESERVED = {
    "register_routes",
    "_handle_get",
    "_handle_post",
    "_handle_put",
    "_handle_delete",
    "_bind_server_globals",
}


def _bind_server_globals() -> None:
    bind_server_globals(globals())


def register_routes(registry: RouteRegistry) -> None:
    registry.exact('GET', ('cv',), _handle_get, auth_required=True, name='documents.cv')
    registry.prefix('GET', ('cv-upload',), _handle_get, auth_required=True, name='documents.cv_upload_status')
    registry.prefix('GET', ('contracts',), _handle_get, auth_required=True, name='documents.contracts')
    registry.prefix('GET', ('documents',), _handle_get, auth_required=True, name='documents.documents')
    registry.prefix('POST', ('documents',), _handle_post, auth_required=True, name='documents.documents.post')
    registry.exact('POST', ('cv-upload',), _handle_post, auth_required=True, name='documents.cv_upload')
    registry.exact('POST', ('profile-photo-upload',), _handle_post, auth_required=True, name='documents.profile_photo_upload')
    registry.prefix('POST', ('ats',), _handle_post, auth_required=True, name='documents.ats')
    registry.prefix('POST', ('runs',), _handle_post, auth_required=True, name='documents.run_generation')
    registry.prefix('PUT', ('documents',), _handle_put, auth_required=True, name='documents.documents.put')


def _handle_get(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["cv"]:
                        user, _ = self._require_identity()
                        metadata = dict(user.metadata or {})
                        cv_text = str(metadata.get("cv_text") or "")
                        # fall back to disk file if metadata not populated yet
                        if not cv_text:
                            cv_path = Path("user_config") / "cv_master.txt"
                            if cv_path.exists():
                                try:
                                    cv_text = cv_path.read_text(encoding="utf-8")
                                except Exception:
                                    cv_text = ""
                        self._send_json({"cv_text": cv_text, "char_count": len(cv_text)})
                        return

    if segments[:1] == ["cv-upload"] and len(segments) == 2:
                        user, _ = self._require_identity()
                        self._send_json(
                            cv_upload_status_payload(
                                application.repositories,
                                user_id=user.user_id,
                                job_id=segments[1],
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["contracts", "phase0"]:
                        self._require_identity()
                        self._send_json(phase0_contract_catalog(), status=HTTPStatus.OK)
                        return

    if segments == ["documents"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                        limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                        run_id = str((query.get("run_id") or [""])[0]).strip()
                        asset_kind = str((query.get("asset_kind") or [""])[0]).strip().lower()
                        group_id = str((query.get("group_id") or [""])[0]).strip().lower()
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        entries = _collect_document_entries(
                            application,
                            user,
                            workspace_id=workspace_id,
                            run_id=run_id,
                            asset_kind=asset_kind,
                        )
                        if group_id:
                            entries = [item for item in entries if str(item.get("group_id") or "").lower() == group_id]
                        paged_entries = entries[offset : offset + limit]
                        self._send_json(
                            {
                                "documents": paged_entries,
                                "groups": _document_group_payloads(entries),
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                            }
                        )
                        return

    if segments[:2] == ["documents", "assets"] and len(segments) == 4 and segments[3] == "download":
                        user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                        document_id = _document_id_for_candidate_asset(segments[2])
                        document = _find_document_entry(application, user, document_id)
                        _assert_document_export_allowed(
                            document,
                            export_anyway=_parse_bool_param(query, "export_anyway"),
                        )
                        file_path, download_name = _resolve_candidate_asset_download(
                            application,
                            user,
                            segments[2],
                        )
                        self._send_file(file_path, download_name=download_name)
                        return

    if segments[:2] == ["documents", "bulk-exports"] and len(segments) == 4 and segments[3] == "download":
                        user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                        bundle_path = _candidate_asset_bundle_dir(user) / f"{segments[2]}.zip"
                        self._send_file(str(bundle_path), download_name=bundle_path.name)
                        return

    return False


def _handle_post(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["documents", "upload"]:
                        user, _ = self._require_identity()
                        content_type_header = str(self.headers.get("Content-Type") or "")
                        if "multipart/form-data" not in content_type_header:
                            raise ValueError("documents/upload requires multipart/form-data content type")
                        content_length = int(self.headers.get("Content-Length", "0"))
                        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
                        filename, file_bytes = _parse_multipart_file(content_type_header, raw_body)
                        if not file_bytes:
                            raise ValueError("No file found in multipart body. Ensure the form field has a filename.")
                        asset_kind = str((query.get("asset_kind") or ["uploaded_document"])[0]).strip() or "uploaded_document"
                        workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        display_name = str((query.get("display_name") or [filename])[0]).strip() or filename
                        tags = [asset_kind]
                        is_cv_asset = asset_kind in {"workspace_cv", "master_career_profile"}
                        document_extraction = extract_document_text(
                            filename,
                            file_bytes,
                            allow_ocr=not is_cv_asset,
                        )
                        asset_metadata: dict[str, Any] = extraction_metadata(document_extraction)
                        if is_cv_asset:
                            cv_text = str(document_extraction.get("text") or "")
                            if not cv_text:
                                warning = " ".join(str(item) for item in document_extraction.get("warnings") or []).strip()
                                detail = f" {warning}" if warning else ""
                                raise ValueError(f"Could not extract any text from uploaded file '{filename}'.{detail}")
                            extraction = _extract_cv_profile_for_upload(cv_text)
                            asset_metadata.update({
                                "parsed_profile": dict(extraction.get("profile") or {}),
                                "profile_extraction": {
                                    "provider": str(extraction.get("provider") or ""),
                                    "model": str(extraction.get("model") or ""),
                                    "warnings": list(extraction.get("warnings") or []),
                                    "extracted_at": str(extraction.get("extracted_at") or ""),
                                },
                            })
                            tags = (
                                ["cv", "workspace_cv"]
                                if asset_kind == "workspace_cv"
                                else ["career_profile", "master_career_profile"]
                            )
                        asset = _store_candidate_asset_upload(
                            application,
                            user,
                            filename=filename,
                            file_bytes=file_bytes,
                            asset_kind=asset_kind,
                            display_name=display_name,
                            workspace_id=workspace_id,
                            role=asset_kind,
                            tags=tags,
                            metadata=asset_metadata,
                        )
                        profile_extraction = dict(asset_metadata.get("profile_extraction") or {})
                        application.emit_event(
                            "document_uploaded",
                            user_id=user.user_id,
                            workspace_id=workspace_id,
                            source="api",
                            route="/documents/upload",
                            asset_kind=asset_kind,
                            mime_type=str(asset.get("mime_type") or ""),
                            char_count=int(asset_metadata.get("source_char_count") or 0),
                            warning_count=len(profile_extraction.get("warnings") or []),
                        )
                        self._send_json({"asset": asset}, status=HTTPStatus.CREATED)
                        return

    if segments == ["cv-upload"]:
                        upload_started = perf_counter()
                        timings_ms: dict[str, float | None] = {
                            "body_read": None,
                            "multipart_parse": None,
                            "dedupe_lookup": None,
                            "r2_storage": None,
                            "turso_write": None,
                            "total": None,
                        }
                        outcome = "failed"
                        error_type = ""
                        response_payload: dict[str, Any] | None = None
                        try:
                            user, _ = self._require_identity()
                            content_type_header = str(self.headers.get("Content-Type") or "")
                            if "multipart/form-data" not in content_type_header:
                                raise ValueError("cv-upload requires multipart/form-data content type")

                            stage_started = perf_counter()
                            try:
                                raw_body = self._read_limited_body(
                                    max_bytes=_MAX_CV_UPLOAD_REQUEST_BYTES,
                                    request_label="CV upload",
                                )
                            finally:
                                timings_ms["body_read"] = round((perf_counter() - stage_started) * 1000, 2)

                            stage_started = perf_counter()
                            try:
                                filename, file_bytes = _parse_multipart_file(content_type_header, raw_body)
                            finally:
                                timings_ms["multipart_parse"] = round((perf_counter() - stage_started) * 1000, 2)
                            if not file_bytes:
                                raise ValueError("No file found in multipart body. Ensure the form field has a filename.")

                            uploaded_asset = _store_candidate_asset_upload(
                                application,
                                user,
                                filename=filename,
                                file_bytes=file_bytes,
                                asset_kind="workspace_cv",
                                display_name=filename or "Workspace CV",
                                role="workspace_cv",
                                tags=["cv", "workspace_cv"],
                                metadata={
                                    "status": CV_STATUS_UPLOADED,
                                },
                                timings_ms=timings_ms,
                            )

                            if _candidate_asset_is_ready(uploaded_asset):
                                processing_run = None
                                status_payload = {
                                    "asset_id": str(uploaded_asset.get("asset_id") or ""),
                                    "job_id": "",
                                    "status": CV_STATUS_READY,
                                    "status_url": "",
                                    "asset": uploaded_asset,
                                    "parsed": dict((uploaded_asset.get("metadata") or {}).get("parsed_profile") or {}),
                                    "cv_text": str((uploaded_asset.get("metadata") or {}).get("source_text") or ""),
                                    "char_count": len(str((uploaded_asset.get("metadata") or {}).get("source_text") or "")),
                                    "extraction": dict((uploaded_asset.get("metadata") or {}).get("profile_extraction") or {}),
                                    "error": "",
                                    "run": {},
                                }
                            else:
                                processing_run, uploaded_asset = enqueue_cv_upload_processing_run(
                                    application.repositories,
                                    user_id=user.user_id,
                                    asset_id=str(uploaded_asset.get("asset_id") or ""),
                                )
                                status_payload = cv_upload_status_payload(
                                    application.repositories,
                                    user_id=user.user_id,
                                    job_id=processing_run.id,
                                )

                            timings_ms["total"] = round((perf_counter() - upload_started) * 1000, 2)
                            status_url = str(status_payload.get("status_url") or "")
                            if not status_url and processing_run is not None:
                                status_url = f"/cv-upload/{processing_run.id}"
                            response_payload = {
                                "asset_id": str(uploaded_asset.get("asset_id") or ""),
                                "job_id": str(status_payload.get("job_id") or ""),
                                "status": str(status_payload.get("status") or "queued"),
                                "status_url": status_url,
                                "filename": filename,
                                "asset": uploaded_asset,
                                "parsed": dict(status_payload.get("parsed") or {}),
                                "cv_text": str(status_payload.get("cv_text") or ""),
                                "char_count": int(status_payload.get("char_count") or 0),
                                "extraction": dict(status_payload.get("extraction") or {}),
                                "timings_ms": timings_ms,
                            }
                            outcome = "success"
                        except _CLIENT_DISCONNECT_ERRORS as exc:
                            outcome = "client_disconnected"
                            error_type = type(exc).__name__
                            raise
                        except Exception as exc:
                            error_type = type(exc).__name__
                            raise
                        finally:
                            timings_ms["total"] = round((perf_counter() - upload_started) * 1000, 2)
                            timing_record = {
                                "event": "cv_upload_timing",
                                "route": "/cv-upload",
                                "outcome": outcome,
                                "timings_ms": timings_ms,
                            }
                            if error_type:
                                timing_record["error_type"] = error_type
                            logging.getLogger("backend.api.cv_upload").info(
                                json.dumps(timing_record, sort_keys=True, separators=(",", ":"))
                            )
                        self._send_json(response_payload, status=HTTPStatus.ACCEPTED)
                        return

    if segments == ["profile-photo-upload"]:
                        user, _ = self._require_identity()
                        content_type_header = str(self.headers.get("Content-Type") or "")
                        if "multipart/form-data" not in content_type_header:
                            raise ValueError("profile-photo-upload requires multipart/form-data content type")
                        content_length = int(self.headers.get("Content-Length", "0"))
                        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
                        filename, file_bytes = _parse_multipart_file(content_type_header, raw_body)
                        if not file_bytes:
                            raise ValueError("No file found in multipart body. Ensure the form field has a filename.")
                        if len(file_bytes) > 2 * 1024 * 1024:
                            raise ValueError("Profile photo must be 2MB or smaller.")
                        extension = _guess_image_extension(filename, file_bytes)
                        if extension not in {".png", ".jpg"}:
                            raise ValueError("Profile photo must be a PNG or JPG image.")
                        photo_path, photo_data_url = _store_profile_photo(user, file_bytes, extension)
                        metadata = dict(user.metadata or {})
                        profile = _merge_profile_metadata(dict(metadata.get("profile") or {}), {}, user)
                        profile["photo_path"] = photo_path
                        profile["photo_data_url"] = photo_data_url
                        if not profile.get("avatar_url"):
                            profile["avatar_url"] = photo_data_url
                        metadata["profile"] = profile
                        user.metadata = metadata
                        user.updated_at = datetime.now(timezone.utc).isoformat()
                        application.repositories.auth_repository.upsert_user(user)
                        self._send_json(
                            {
                                "photo_path": photo_path,
                                "photo_data_url": photo_data_url,
                            },
                            status=HTTPStatus.CREATED,
                        )
                        return

    payload = self._read_json_body()

    if segments == ["ats", "export-gate", "evaluate"]:
                        self._require_identity()
                        gate = _evaluate_ats_export_gate_payload(
                            payload,
                            export_anyway=bool(payload.get("export_anyway")),
                        )
                        self._send_json(gate, status=HTTPStatus.OK)
                        return

    if segments == ["documents", "bulk-export"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                        bundle = _create_bulk_export_bundle(
                            application,
                            user,
                            [str(item) for item in payload.get("document_ids") or [] if str(item).strip()],
                            label=str(payload.get("label") or ""),
                            export_anyway=bool(payload.get("export_anyway")),
                        )
                        self._send_json(bundle, status=HTTPStatus.CREATED)
                        return

    if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "excluded-jobs" and segments[4] == "generate-documents":
                        user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                        context = self._auth_context()
                        run = application.get_run(segments[1])
                        if not application.user_can_access_workspace(user, run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        job_id = str(segments[3] or "").strip()
                        if not job_id:
                            raise ValueError("job_id is required")
                        check_and_increment_quota(
                            application,
                            user.user_id,
                            "cv_exports_per_month",
                            context.plan_id,
                            route="/runs/.../generate-documents",
                            quota_overrides=context.quota_overrides,
                        )
                        execution_mode = str(payload.get("execution_mode") or "queued").strip().lower()
                        document_run = application.requeue_job_for_generation(
                            run_id=segments[1],
                            job_id=job_id,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max(1, int(payload.get("max_attempts") or 1)),
                            execute=execution_mode == "sync",
                            notes=str(payload.get("notes") or ""),
                        )
                        reviewer_name = user.display_name or user.email or user.user_id
                        reason_summary = str(payload.get("reason_summary") or payload.get("notes") or "")
                        source_stage = str(payload.get("source_stage") or "rejected_review")
                        review = _upsert_rejected_review_override(
                            application,
                            run_id=segments[1],
                            job_id=job_id,
                            reviewer=reviewer_name,
                            reason_summary=reason_summary,
                            source_stage=source_stage,
                            notes=str(payload.get("notes") or ""),
                            requeue_run_id=document_run.id,
                        )
                        self._send_json(
                            {
                                "run": document_run.to_dict(),
                                "review": review,
                            },
                            status=HTTPStatus.CREATED,
                        )
                        return

    return False


def _handle_put(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    payload = self._read_json_body()

    if segments[:2] == ["documents", "assets"] and len(segments) == 4 and segments[3] == "sections":
                        user, _ = self._require_identity()
                        document = _update_candidate_asset_section_decisions(
                            application,
                            user,
                            segments[2],
                            payload.get("section_decisions") or payload.get("decisions") or [],
                        )
                        self._send_json({"document": document}, status=HTTPStatus.OK)
                        return

    return False
