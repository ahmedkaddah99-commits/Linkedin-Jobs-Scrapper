# ruff: noqa: F821
from __future__ import annotations

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.api.routes.route_support import bind_server_globals

# Tracker, referrals, Gmail, outreach, rejected jobs, and people discovery.
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
    registry.exact('GET', ('tracker', 'email-integration', 'google', 'callback'), _handle_get, auth_required=False, name='tracker.google.callback')
    registry.prefix('GET', ('referrals',), _handle_get, auth_required=True, name='tracker.referrals')
    registry.prefix('GET', ('tracker',), _handle_get, auth_required=True, name='tracker.tracker')
    registry.prefix('GET', ('rejected-jobs',), _handle_get, auth_required=True, name='tracker.rejected_jobs')
    registry.prefix('GET', ('runs',), _handle_get, auth_required=True, name='tracker.people_discovery')
    registry.prefix('POST', ('tracker',), _handle_post, auth_required=True, name='tracker.tracker.post')
    registry.prefix('POST', ('referrals',), _handle_post, auth_required=True, name='tracker.referrals.post')
    registry.prefix('POST', ('outreach',), _handle_post, auth_required=True, name='tracker.outreach.post')
    registry.prefix('POST', ('runs',), _handle_post, auth_required=True, name='tracker.people_discovery.post')
    registry.prefix('POST', ('rejected-jobs',), _handle_post, auth_required=True, name='tracker.rejected_jobs.post')
    registry.prefix('PUT', ('referrals',), _handle_put, auth_required=True, name='tracker.referrals.put')
    registry.prefix('PUT', ('tracker',), _handle_put, auth_required=True, name='tracker.tracker.put')
    registry.prefix('DELETE', ('referrals',), _handle_delete, auth_required=True, name='tracker.referrals.delete')
    registry.prefix('DELETE', ('tracker',), _handle_delete, auth_required=True, name='tracker.tracker.delete')


def _handle_get(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["tracker", "email-integration", "google", "callback"]:
                        state = str((query.get("state") or [""])[0]).strip()
                        user_id, state_nonce = _parse_tracker_google_oauth_state(state)
                        if not user_id or not state_nonce:
                            self._send_html(
                                tracker_google_oauth_callback_message(
                                    success=False,
                                    message="The Google authorization callback is missing a valid tracker state.",
                                ),
                                status=HTTPStatus.BAD_REQUEST,
                            )
                            return
                        try:
                            user = application.get_user(user_id)
                        except KeyError:
                            self._send_html(
                                tracker_google_oauth_callback_message(
                                    success=False,
                                    message="The tracker user for this Google authorization request no longer exists.",
                                ),
                                status=HTTPStatus.NOT_FOUND,
                            )
                            return
                        current_config = _get_tracker_email_config(user)
                        if not tracker_google_oauth_state_is_valid(current_config, expected_state=state_nonce):
                            self._send_html(
                                tracker_google_oauth_callback_message(
                                    success=False,
                                    message="This Google authorization request is expired or no longer valid.",
                                ),
                                status=HTTPStatus.BAD_REQUEST,
                            )
                            return
                        provider_error = str((query.get("error") or [""])[0]).strip()
                        if provider_error:
                            failed_config = mark_google_tracker_authorization_error(
                                current_config,
                                error_message=f"Google authorization failed: {provider_error}",
                            )
                            _persist_tracker_email_config(application, user, failed_config)
                            self._send_html(
                                tracker_google_oauth_callback_message(
                                    success=False,
                                    message=f"Google authorization failed: {provider_error}",
                                ),
                                status=HTTPStatus.BAD_REQUEST,
                            )
                            return
                        code = str((query.get("code") or [""])[0]).strip()
                        if not code:
                            failed_config = mark_google_tracker_authorization_error(
                                current_config,
                                error_message="Google did not return an authorization code.",
                            )
                            _persist_tracker_email_config(application, user, failed_config)
                            self._send_html(
                                tracker_google_oauth_callback_message(
                                    success=False,
                                    message="Google did not return an authorization code.",
                                ),
                                status=HTTPStatus.BAD_REQUEST,
                            )
                            return
                        try:
                            token_payload = exchange_google_tracker_oauth_code(
                                code=code,
                                redirect_uri=str(current_config.get("oauth_redirect_uri") or self._tracker_google_callback_uri()),
                            )
                            access_token = str(token_payload.get("access_token") or "").strip()
                            refresh_token = str(token_payload.get("refresh_token") or "").strip() or _resolve_tracker_email_refresh_token(
                                application,
                                current_config,
                            )
                            if not access_token:
                                raise ValueError("Google did not return an access token.")
                            if not refresh_token:
                                raise ValueError(
                                    "Google did not return a refresh token. Disconnect and authorize again."
                                )
                            profile_payload = fetch_google_tracker_profile(access_token=access_token)
                            email_address = str(profile_payload.get("emailAddress") or current_config.get("email_address") or "").strip()
                            updated_config = complete_google_tracker_authorization(
                                current_config,
                                email_address=email_address,
                            )
                            updated_config["access_token_secret_id"] = _upsert_tracker_email_access_token_secret(
                                application,
                                user,
                                updated_config,
                                access_token,
                            )
                            updated_config["refresh_token_secret_id"] = _upsert_tracker_email_refresh_token_secret(
                                application,
                                user,
                                updated_config,
                                refresh_token,
                            )
                            expires_in = int(token_payload.get("expires_in") or 3600)
                            updated_config["access_token_expires_at"] = utc_plus_seconds(expires_in)
                            _persist_tracker_email_config(application, user, updated_config)
                            self._send_html(
                                tracker_google_oauth_callback_message(
                                    success=True,
                                    message=f"{email_address or 'Your Gmail account'} is now connected to the tracker.",
                                ),
                                status=HTTPStatus.OK,
                            )
                            return
                        except ValueError as exc:
                            failed_config = mark_google_tracker_authorization_error(current_config, error_message=str(exc))
                            _persist_tracker_email_config(application, user, failed_config)
                            self._send_html(
                                tracker_google_oauth_callback_message(success=False, message=str(exc)),
                                status=HTTPStatus.BAD_REQUEST,
                            )
                            return

    if segments == ["referrals"]:
                        user, _ = self._require_identity()
                        limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        contacts = application.list_referral_contacts(user.user_id)
                        paged_contacts = contacts[offset : offset + limit]
                        self._send_json(
                            {
                                "contacts": [contact.to_dict() for contact in paged_contacts],
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_contacts)),
                            }
                        )
                        return

    if segments == ["referrals", "outreach-statuses"]:
                        user, _ = self._require_identity()
                        limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        items = _collect_referral_outreach_entries(
                            application,
                            user,
                            contact_id=str((query.get("contact_id") or [""])[0]).strip(),
                            run_id=str((query.get("run_id") or [""])[0]).strip(),
                            job_id=str((query.get("job_id") or [""])[0]).strip(),
                        )
                        paged_items = items[offset : offset + limit]
                        self._send_json(
                            {
                                "items": paged_items,
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_items)),
                            }
                        )
                        return

    if segments[:1] == ["referrals"] and len(segments) == 2:
                        user, _ = self._require_identity()
                        self._send_json(application.get_referral_contact(user.user_id, segments[1]).to_dict())
                        return

    if segments == ["tracker"]:
                        user, _ = self._require_identity()
                        entries = _collect_tracker_entries(application, user)
                        if _parse_bool_param(query, "explicit_only"):
                            entries = [item for item in entries if bool(item.get("is_explicit_application"))]
                        self._send_json(
                            {
                                "items": entries,
                                "columns": TRACKER_TABLE_COLUMNS,
                                "excel_baseline_columns": TRACKER_EXCEL_BASELINE_COLUMNS,
                                "meta": self._pagination_meta(limit=len(entries), offset=0, returned=len(entries)),
                            }
                        )
                        return

    if segments == ["tracker", "email-integration"]:
                        user, _ = self._require_identity()
                        self._send_json(_tracker_email_integration_payload(application, user), status=HTTPStatus.OK)
                        return

    if segments == ["rejected-jobs"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_REVIEWS_READ)
                        limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                        run_id = str((query.get("run_id") or [""])[0]).strip()
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        entries = _collect_rejected_job_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                        paged_entries = entries[offset : offset + limit]
                        self._send_json(
                            {
                                "items": paged_entries,
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                            }
                        )
                        return

    if (
                        segments[:1] == ["runs"]
                        and len(segments) == 7
                        and segments[2] == "jobs"
                        and segments[3] == "by-id"
                        and segments[5] == "people-discovery"
                        and segments[6] == "status"
                    ):
                        user, _ = self._require_identity()
                        run = application.get_run(segments[1])
                        if not application.user_can_access_workspace(user, run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        self._send_json(
                            application.get_relevant_people_discovery_status(
                                user_id=user.user_id,
                                run_id=segments[1],
                                job_id=segments[4],
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if (
                        segments[:1] == ["runs"]
                        and len(segments) == 7
                        and segments[2] == "jobs"
                        and segments[3] == "by-id"
                        and segments[5] == "people-discovery"
                        and segments[6] == "results"
                    ):
                        user, _ = self._require_identity()
                        run = application.get_run(segments[1])
                        if not application.user_can_access_workspace(user, run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        self._send_json(
                            application.get_relevant_people_discovery_results(
                                user_id=user.user_id,
                                run_id=segments[1],
                                job_id=segments[4],
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    return False


def _handle_post(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    payload = self._read_json_body()

    if segments == ["tracker", "email-integration", "detections", "approve"]:
                        user, _ = self._require_identity()
                        current_config = _get_tracker_email_config(user)
                        detections_payload = payload.get("detections")
                        if not isinstance(detections_payload, list):
                            detections_payload = [payload.get("detection") or payload]
                        approved: list[dict] = []
                        resolved_detection_ids: set[str] = set()
                        applications = _load_external_tracker_applications(user)
                        for detection_payload in detections_payload:
                            if not isinstance(detection_payload, dict):
                                continue
                            detection = normalize_gmail_application_detection(
                                {
                                    **detection_payload,
                                    "approval_state": "approved",
                                }
                            )
                            detection_id = _gmail_detection_id(detection)
                            if detection_id:
                                detection["detection_id"] = detection_id
                                resolved_detection_ids.add(detection_id)
                            review_id = str(detection.get("metadata", {}).get("review_id") or "").strip()
                            if review_id:
                                review = application.get_review(review_id)
                                previously_actionable = review_is_actionable_tracker_item(review)
                                existing_placed_in_tracker_at = review_placed_in_tracker_at(
                                    review,
                                    include_legacy_fallback=False,
                                )
                                run = application.get_run(review.run_id)
                                if not application.user_can_access_workspace(user, run.workspace_id):
                                    raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                                review_meta = dict(review.metadata or {})
                                application_status = normalize_application_status(
                                    detection["status"]["suggested_application_status"]
                                )
                                review_meta["application_status"] = application_status
                                review_meta["tracker_status"] = legacy_tracker_status_for_application_status(application_status)
                                if application_status == "Applied":
                                    review_meta["email_confirmed"] = True
                                if application_status == "Rejected" and not review_meta.get("rejected_at"):
                                    review_meta["rejected_at"] = detection["source_email"]["sent_at"] or datetime.now(timezone.utc).isoformat()
                                review_meta["tracker_email_sync"] = {
                                    "message_id": detection["source_email"]["message_id"],
                                    "subject": detection["source_email"]["subject"],
                                    "from_address": detection["source_email"]["from_address"],
                                    "status": review_meta["tracker_status"],
                                    "suggested_application_status": application_status,
                                    "confidence": detection["status"]["confidence"],
                                    "evidence": list(detection["status"]["evidence"] or []),
                                    "provider_id": str(detection.get("metadata", {}).get("provider_id") or current_config["provider_id"]),
                                    "synced_at": datetime.now(timezone.utc).isoformat(),
                                    "approval_state": "approved",
                                }
                                review.metadata = review_meta
                                ensure_review_placed_in_tracker_at(
                                    review,
                                    previously_actionable=previously_actionable,
                                    existing_placed_in_tracker_at=existing_placed_in_tracker_at,
                                )
                                application.repositories.review_store.upsert_review(review)
                                approved.append({"review_id": review_id, "application_status": application_status})
                                continue
                            external_application = _upsert_external_tracker_application_from_detection(applications, detection)
                            approved.append(external_application)
                        updated_config = dict(current_config)
                        updated_config["pending_detections"] = _merge_pending_tracker_detections(
                            existing=current_config.get("pending_detections") or [],
                            remove_ids=resolved_detection_ids,
                        )
                        if updated_config.get("last_sync_summary"):
                            updated_config["last_sync_summary"] = {
                                **dict(updated_config.get("last_sync_summary") or {}),
                                "pending_review": len(updated_config["pending_detections"]),
                            }
                        refreshed_user = _persist_external_tracker_applications(application, user, applications)
                        refreshed_user = _persist_tracker_email_config(application, refreshed_user, updated_config)
                        self._send_json(
                            {
                                "approved": approved,
                                "tracker": {
                                    "items": _collect_tracker_entries(application, refreshed_user),
                                    "meta": self._pagination_meta(limit=len(approved), offset=0, returned=len(approved)),
                                },
                                "integration": _tracker_email_integration_payload(application, refreshed_user),
                            },
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["tracker", "email-integration", "detections", "dismiss"]:
                        user, _ = self._require_identity()
                        current_config = _get_tracker_email_config(user)
                        detections_payload = payload.get("detections")
                        if not isinstance(detections_payload, list):
                            detections_payload = [payload.get("detection") or payload]
                        dismissed: list[dict] = []
                        resolved_detection_ids: set[str] = set()
                        for detection_payload in detections_payload:
                            if not isinstance(detection_payload, dict):
                                continue
                            detection = normalize_gmail_application_detection(
                                {
                                    **detection_payload,
                                    "approval_state": "dismissed",
                                }
                            )
                            detection_id = _gmail_detection_id(detection)
                            if detection_id:
                                detection["detection_id"] = detection_id
                                resolved_detection_ids.add(detection_id)
                            dismissed.append(detection)
                        updated_config = dict(current_config)
                        updated_config["pending_detections"] = _merge_pending_tracker_detections(
                            existing=current_config.get("pending_detections") or [],
                            remove_ids=resolved_detection_ids,
                        )
                        if updated_config.get("last_sync_summary"):
                            updated_config["last_sync_summary"] = {
                                **dict(updated_config.get("last_sync_summary") or {}),
                                "pending_review": len(updated_config["pending_detections"]),
                            }
                        refreshed_user = _persist_tracker_email_config(application, user, updated_config)
                        self._send_json(
                            {
                                "dismissed": dismissed,
                                "integration": _tracker_email_integration_payload(application, refreshed_user),
                            },
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["referrals"]:
                        user, _ = self._require_identity()
                        self._send_json(
                            application.upsert_referral_contact(user_id=user.user_id, payload=payload).to_dict(),
                            status=HTTPStatus.CREATED,
                        )
                        return

    if segments == ["referrals", "import"]:
                        user, _ = self._require_identity()
                        self._send_json(
                            application.import_referral_contacts(
                                user_id=user.user_id,
                                csv_text=str(payload.get("csv_text") or ""),
                                source_kind=str(payload.get("source_kind") or "linkedin_csv"),
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["referrals", "outreach-status"]:
                        user, _ = self._require_identity()
                        record, previous_status = _save_referral_outreach_status_from_payload(application, user, payload)
                        application.emit_event(
                            "outreach_status_changed",
                            user_id=user.user_id,
                            run_id=str(record.get("run_id") or ""),
                            job_id=str(record.get("job_id") or ""),
                            source="api",
                            route="/referrals/outreach-status",
                            contact_id=str(record.get("contact_id") or ""),
                            previous_status=previous_status,
                            next_status=str(record.get("outreach_status") or ""),
                        )
                        self._send_json(
                            record,
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["outreach", "referral-draft"]:
                        user, _ = self._require_identity()
                        context = self._auth_context()
                        check_and_increment_quota(
                            application,
                            user.user_id,
                            "referral_drafts_per_month",
                            context.plan_id,
                            route="/outreach/referral-draft",
                            quota_overrides=context.quota_overrides,
                        )
                        draft = application.generate_referral_outreach(
                            user_id=user.user_id,
                            run_id=str(payload.get("run_id") or ""),
                            job_id=str(payload.get("job_id") or ""),
                            contact_id=str(payload.get("contact_id") or ""),
                        )
                        draft_contact = dict(draft.get("contact") or {})
                        application.emit_event(
                            "referral_draft_generated",
                            user_id=user.user_id,
                            run_id=str(payload.get("run_id") or ""),
                            job_id=str(payload.get("job_id") or ""),
                            source="api",
                            route="/outreach/referral-draft",
                            contact_id=str(draft_contact.get("contact_id") or payload.get("contact_id") or ""),
                            draft_type="referral",
                        )
                        self._send_json(
                            draft,
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["outreach", "hiring-manager-draft"]:
                        user, _ = self._require_identity()
                        self._send_json(
                            application.generate_hiring_manager_outreach(
                                user_id=user.user_id,
                                run_id=str(payload.get("run_id") or ""),
                                job_id=str(payload.get("job_id") or ""),
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["outreach", "target-contact-discovery"]:
                        user, _ = self._require_identity()
                        self._send_json(
                            application.generate_target_contact_discovery(
                                user_id=user.user_id,
                                run_id=str(payload.get("run_id") or ""),
                                job_id=str(payload.get("job_id") or ""),
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if (
                        segments[:1] == ["runs"]
                        and len(segments) == 7
                        and segments[2] == "jobs"
                        and segments[3] == "by-id"
                        and segments[5] == "people-discovery"
                        and segments[6] == "start"
                    ):
                        user, _ = self._require_identity()
                        run = application.get_run(segments[1])
                        if not application.user_can_access_workspace(user, run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        self._send_json(
                            application.start_relevant_people_discovery(
                                user_id=user.user_id,
                                run_id=segments[1],
                                job_id=segments[4],
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if (
                        segments[:1] == ["runs"]
                        and len(segments) == 7
                        and segments[2] == "jobs"
                        and segments[3] == "by-id"
                        and segments[5] == "people-discovery"
                        and segments[6] in {"confirm", "reject", "save-for-outreach"}
                    ):
                        user, _ = self._require_identity()
                        run = application.get_run(segments[1])
                        if not application.user_can_access_workspace(user, run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        person_id = str(payload.get("person_id") or payload.get("personId") or "").strip()
                        if not person_id:
                            raise ValueError("person_id is required")
                        next_status = {
                            "confirm": "confirmed",
                            "reject": "rejected",
                            "save-for-outreach": "saved_for_outreach",
                        }[segments[6]]
                        self._send_json(
                            application.set_relevant_people_status(
                                user_id=user.user_id,
                                run_id=segments[1],
                                job_id=segments[4],
                                person_id=person_id,
                                status=next_status,
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["rejected-jobs", "requeue"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                        run_id = str(payload.get("run_id") or "").strip()
                        job_id = str(payload.get("job_id") or "").strip()
                        if not run_id or not job_id:
                            raise ValueError("run_id and job_id are required")
                        original_run = application.get_run(run_id)
                        if not application.user_can_access_workspace(user, original_run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{original_run.workspace_id}'.")
                        execution_mode = str(payload.get("execution_mode") or "queued").strip().lower()
                        requeued_run = application.requeue_job_for_generation(
                            run_id=run_id,
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
                            run_id=run_id,
                            job_id=job_id,
                            reviewer=reviewer_name,
                            reason_summary=reason_summary,
                            source_stage=source_stage,
                            notes=str(payload.get("notes") or ""),
                            requeue_run_id=requeued_run.id,
                        )
                        self._send_json({"run": requeued_run.to_dict(), "review": review}, status=HTTPStatus.CREATED)
                        return

    if segments == ["tracker", "email-integration", "google", "start"]:
                        user, _ = self._require_identity()
                        merged_payload = {
                            **_get_tracker_email_config(user),
                            "provider_id": "gmail",
                            "auth_strategy": "google_oauth",
                        }
                        if "folder" in payload:
                            merged_payload["folder"] = str(payload.get("folder") or "INBOX")
                        if "max_messages" in payload and payload.get("max_messages") is not None:
                            merged_payload["max_messages"] = payload.get("max_messages")
                        if "scan_window" in payload and payload.get("scan_window") is not None:
                            merged_payload["scan_window"] = normalize_gmail_scan_window(payload.get("scan_window"))
                        current_config = normalize_tracker_email_config(merged_payload)
                        redirect_uri = self._tracker_google_callback_uri()
                        state_nonce, oauth_state = _build_tracker_google_oauth_state(user)
                        authorization_url = build_google_tracker_authorization_url(
                            state=oauth_state,
                            redirect_uri=redirect_uri,
                        )
                        updated_config = begin_google_tracker_authorization(
                            {**current_config, "oauth_state": state_nonce},
                            redirect_uri=redirect_uri,
                            authorization_url=authorization_url,
                        )
                        updated_config["oauth_state"] = state_nonce
                        refreshed_user = _persist_tracker_email_config(application, user, updated_config)
                        self._send_json(
                            {
                                "authorization_url": authorization_url,
                                "expires_at": updated_config["oauth_state_expires_at"],
                                "integration": _tracker_email_integration_payload(application, refreshed_user),
                            },
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["tracker", "email-integration", "sync"]:
                        user, _ = self._require_identity()
                        current_config = _get_tracker_email_config(user)
                        if "scan_window" in payload and payload.get("scan_window") is not None:
                            current_config["scan_window"] = normalize_gmail_scan_window(payload.get("scan_window"))
                        if "max_messages" in payload and payload.get("max_messages") is not None:
                            current_config["max_messages"] = payload.get("max_messages")
                        tracker_items = _collect_tracker_entries(application, user)
                        try:
                            updated_config = dict(current_config)
                            if str(current_config.get("auth_strategy") or "") == "google_oauth":
                                refresh_token = _resolve_tracker_email_refresh_token(application, current_config)
                                access_token = _resolve_tracker_email_access_token(application, current_config)
                                if refresh_token:
                                    token_payload = refresh_google_tracker_access_token(refresh_token=refresh_token)
                                    access_token = str(token_payload.get("access_token") or "").strip()
                                    if not access_token:
                                        raise ValueError("Google did not return an access token during refresh.")
                                    updated_config["access_token_secret_id"] = _upsert_tracker_email_access_token_secret(
                                        application,
                                        user,
                                        updated_config,
                                        access_token,
                                    )
                                    updated_config["access_token_expires_at"] = utc_plus_seconds(
                                        int(token_payload.get("expires_in") or 3600)
                                    )
                                result = sync_tracker_gmail(
                                    application=application,
                                    user=user,
                                    tracker_items=tracker_items,
                                    config=updated_config,
                                    access_token=access_token,
                                )
                            else:
                                password = _resolve_tracker_email_password(application, current_config)
                                result = sync_tracker_email(
                                    application=application,
                                    user=user,
                                    tracker_items=tracker_items,
                                    config=current_config,
                                    password=password,
                                )
                        except ValueError as exc:
                            failed_config = dict(current_config)
                            error_text = str(exc)
                            failed_config["last_error"] = error_text
                            if "invalid_grant" in error_text.lower() or "expired or revoked" in error_text.lower():
                                failed_config["connected"] = False
                                failed_config["authorization_state"] = "reauthorization_required"
                            failed_config["updated_at"] = datetime.now(timezone.utc).isoformat()
                            _persist_tracker_email_config(application, user, failed_config)
                            raise
                        updated_config["processed_message_ids"] = result["processed_message_ids"]
                        updated_config["last_sync_at"] = result["synced_at"]
                        updated_config["updated_at"] = result["synced_at"]
                        updated_config["last_error"] = ""
                        updated_config["last_sync_summary"] = dict(result["summary"] or {})
                        updated_config["pending_detections"] = _merge_pending_tracker_detections(
                            existing=current_config.get("pending_detections") or [],
                            additions=[
                                detection
                                for detection in result.get("detections") or []
                                if isinstance(detection, dict)
                                and str(detection.get("status", {}).get("approval_state") or "") == "pending_review"
                            ],
                        )
                        updated_config["authorization_state"] = "authorized"
                        if result.get("history_id"):
                            updated_config["history_id"] = str(result.get("history_id") or "")
                        refreshed_user = _persist_tracker_email_config(application, user, updated_config)
                        self._send_json(
                            {
                                "integration": _tracker_email_integration_payload(application, refreshed_user),
                                "result": result,
                            },
                            status=HTTPStatus.OK,
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

    if segments == ["referrals", "outreach-status"]:
                        user, _ = self._require_identity()
                        record, previous_status = _save_referral_outreach_status_from_payload(application, user, payload)
                        application.emit_event(
                            "outreach_status_changed",
                            user_id=user.user_id,
                            run_id=str(record.get("run_id") or ""),
                            job_id=str(record.get("job_id") or ""),
                            source="api",
                            route="/referrals/outreach-status",
                            contact_id=str(record.get("contact_id") or ""),
                            previous_status=previous_status,
                            next_status=str(record.get("outreach_status") or ""),
                        )
                        self._send_json(
                            record,
                            status=HTTPStatus.OK,
                        )
                        return

    if segments[:1] == ["referrals"] and len(segments) == 2:
                        user, _ = self._require_identity()
                        self._send_json(
                            application.upsert_referral_contact(
                                user_id=user.user_id,
                                payload=payload,
                                contact_id=segments[1],
                            ).to_dict(),
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["tracker", "email-integration"]:
                        user, _ = self._require_identity()
                        existing_config = _get_tracker_email_config(user)
                        raw_password = str(payload.get("password") or "").strip()
                        merged_payload = {
                            **existing_config,
                            **{key: value for key, value in payload.items() if key != "password" and value is not None},
                        }
                        if raw_password and not str(payload.get("auth_strategy") or "").strip():
                            merged_payload["auth_strategy"] = "legacy_imap_password"
                        merged_config = normalize_tracker_email_config(merged_payload)
                        connection_fingerprint = (
                            existing_config.get("provider_id"),
                            existing_config.get("email_address"),
                            existing_config.get("imap_host"),
                            existing_config.get("imap_port"),
                            existing_config.get("folder"),
                        )
                        next_fingerprint = (
                            merged_config.get("provider_id"),
                            merged_config.get("email_address"),
                            merged_config.get("imap_host"),
                            merged_config.get("imap_port"),
                            merged_config.get("folder"),
                        )
                        now_iso = datetime.now(timezone.utc).isoformat()
                        if merged_config.get("auth_strategy") == "google_oauth":
                            merged_config["provider_id"] = "gmail"
                        else:
                            password = raw_password or _resolve_tracker_email_password(application, existing_config)
                            test_tracker_email_connection(merged_config, password)
                            if raw_password:
                                merged_config["password_secret_id"] = _upsert_tracker_email_password_secret(
                                    application,
                                    user,
                                    merged_config,
                                    raw_password,
                                )
                            else:
                                merged_config["password_secret_id"] = str(existing_config.get("password_secret_id") or "")
                            merged_config["connected_at"] = (
                                str(existing_config.get("connected_at") or now_iso)
                                if connection_fingerprint == next_fingerprint
                                else now_iso
                            )
                        merged_config["updated_at"] = now_iso
                        merged_config["last_error"] = ""
                        if connection_fingerprint != next_fingerprint:
                            merged_config["processed_message_ids"] = []
                            merged_config["last_sync_at"] = ""
                            merged_config["last_sync_summary"] = {}
                            merged_config["pending_detections"] = []
                        refreshed_user = _persist_tracker_email_config(application, user, merged_config)
                        self._send_json(_tracker_email_integration_payload(application, refreshed_user), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["tracker"] and len(segments) == 2:
                        # PUT /tracker/:review_id — update tracker_status, email_confirmed, rejection_note
                        user, _ = self._require_identity()
                        if segments[1].startswith("external_"):
                            existing_external = next(
                                (
                                    item
                                    for item in _load_external_tracker_applications(user)
                                    if str(item.get("application_id") or "") == segments[1]
                                ),
                                None,
                            )
                            previous_status = normalize_application_status(
                                (existing_external or {}).get("application_status")
                                or (existing_external or {}).get("tracker_status"),
                                default="Unknown",
                            )
                            previous_email_confirmed = bool((existing_external or {}).get("email_confirmed") or False)
                            _, updated_external = _update_external_tracker_application(
                                application,
                                user,
                                segments[1],
                                payload,
                            )
                            next_status = normalize_application_status(
                                updated_external.get("application_status") or updated_external.get("tracker_status"),
                                default="Unknown",
                            )
                            next_email_confirmed = bool(updated_external.get("email_confirmed") or False)
                            if previous_status != next_status:
                                application.repositories.review_store.append_application_status_history(
                                    review_id=str(
                                        updated_external.get("review_id")
                                        or updated_external.get("application_id")
                                        or segments[1]
                                    ),
                                    user_id=user.user_id,
                                    from_status=previous_status,
                                    to_status=next_status,
                                    changed_at=str(updated_external.get("updated_at") or ""),
                                    source="manual",
                                )
                            if previous_status != next_status or previous_email_confirmed != next_email_confirmed:
                                application.emit_event(
                                    "application_status_updated",
                                    user_id=user.user_id,
                                    job_id=str(updated_external.get("application_id") or ""),
                                    review_id=str(updated_external.get("review_id") or updated_external.get("application_id") or ""),
                                    source="api",
                                    route=f"/tracker/{segments[1]}",
                                    from_status=previous_status,
                                    to_status=next_status,
                                    explicit=True,
                                    email_confirmed=next_email_confirmed,
                                )
                            self._send_json(
                                {
                                    "review_id": updated_external["review_id"],
                                    "application_id": updated_external["application_id"],
                                    "tracker_status": str(updated_external.get("tracker_status") or ""),
                                    "application_status": next_status,
                                    "email_confirmed": next_email_confirmed,
                                    "is_explicit_application": _is_explicit_tracker_application(
                                        tracker_status=updated_external.get("tracker_status"),
                                        email_confirmed=updated_external.get("email_confirmed"),
                                    ),
                                    "rejection_note": str(updated_external.get("rejection_note") or ""),
                                    "notes": str(updated_external.get("notes") or ""),
                                    "placed_in_tracker_at": str(updated_external.get("placed_in_tracker_at") or ""),
                                    "updated_at": str(updated_external.get("updated_at") or ""),
                                },
                                status=HTTPStatus.OK,
                            )
                            return
                        review = application.get_review(segments[1])
                        previously_actionable = review_is_actionable_tracker_item(review)
                        existing_placed_in_tracker_at = review_placed_in_tracker_at(
                            review,
                            include_legacy_fallback=False,
                        )
                        run = application.get_run(review.run_id)
                        if not application.user_can_access_workspace(user, run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        review_meta = dict(review.metadata or {})
                        previous_status = normalize_application_status(
                            review_meta.get("application_status") or review_meta.get("tracker_status"),
                            default="Not applied" if review.decision == "approved" else "Unknown",
                        )
                        previous_email_confirmed = bool(review_meta.get("email_confirmed") or False)
                        allowed_tracker_statuses = {
                            "applied",
                            "email_confirmed",
                            "interview_invited",
                            "rejected",
                            "not_applied",
                            "offer",
                            "withdrawn",
                            "unknown",
                        }
                        if "tracker_status" in payload:
                            new_status = str(payload["tracker_status"]).strip().lower()
                            if new_status and new_status not in allowed_tracker_statuses:
                                raise ValueError(f"tracker_status must be one of: {sorted(allowed_tracker_statuses)}")
                            review_meta["tracker_status"] = new_status
                            review_meta["application_status"] = normalize_application_status(new_status)
                        if "application_status" in payload:
                            application_status = normalize_application_status(payload.get("application_status"), default="")
                            if not application_status:
                                raise ValueError("application_status is required")
                            review_meta["application_status"] = application_status
                            review_meta["tracker_status"] = legacy_tracker_status_for_application_status(application_status)
                        if "email_confirmed" in payload:
                            review_meta["email_confirmed"] = bool(payload["email_confirmed"])
                        if "rejection_note" in payload:
                            review_meta["rejection_note"] = str(payload["rejection_note"])
                        if "notes" in payload:
                            review.notes = str(payload.get("notes") or "")
                            review_meta["notes"] = review.notes
                        if (
                            review_meta.get("tracker_status") == "rejected"
                            or review_meta.get("application_status") == "Rejected"
                        ) and not review_meta.get("rejected_at"):
                            review_meta["rejected_at"] = datetime.now(timezone.utc).isoformat()
                        review.metadata = review_meta
                        placed_in_tracker_at = ensure_review_placed_in_tracker_at(
                            review,
                            previously_actionable=previously_actionable,
                            existing_placed_in_tracker_at=existing_placed_in_tracker_at,
                        )
                        next_status = normalize_application_status(
                            review_meta.get("application_status") or review_meta.get("tracker_status"),
                            default="Not applied" if review.decision == "approved" else "Unknown",
                        )
                        if previous_status != next_status:
                            application.repositories.review_store.upsert_review(
                                review,
                                application_status_history={
                                    "review_id": review.review_id,
                                    "user_id": user.user_id,
                                    "from_status": previous_status,
                                    "to_status": next_status,
                                    "source": "manual",
                                },
                            )
                        else:
                            application.repositories.review_store.upsert_review(review)
                        next_email_confirmed = bool(review_meta.get("email_confirmed") or False)
                        if previous_status != next_status or previous_email_confirmed != next_email_confirmed:
                            application.emit_event(
                                "application_status_updated",
                                user_id=user.user_id,
                                workspace_id=run.workspace_id,
                                run_id=run.id,
                                job_id=review.job_id,
                                review_id=review.review_id,
                                source="api",
                                route=f"/tracker/{review.review_id}",
                                from_status=previous_status,
                                to_status=next_status,
                                explicit=True,
                                email_confirmed=next_email_confirmed,
                            )
                        self._send_json(
                            {
                                "review_id": review.review_id,
                                "tracker_status": str(review_meta.get("tracker_status") or ""),
                                "application_status": next_status,
                                "email_confirmed": next_email_confirmed,
                                "is_explicit_application": _is_explicit_tracker_application(
                                    tracker_status=review_meta.get("tracker_status"),
                                    email_confirmed=review_meta.get("email_confirmed"),
                                ),
                                "rejection_note": str(review_meta.get("rejection_note") or ""),
                                "notes": str(review.notes or review_meta.get("notes") or ""),
                                "rejected_at": str(review_meta.get("rejected_at") or ""),
                                "placed_in_tracker_at": placed_in_tracker_at,
                                "updated_at": review.updated_at,
                            },
                            status=HTTPStatus.OK,
                        )
                        return

    return False


def _handle_delete(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments[:1] == ["referrals"] and len(segments) == 2:
                        user, _ = self._require_identity()
                        application.delete_referral_contact(user.user_id, segments[1])
                        self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments == ["tracker", "email-integration"]:
                        user, _ = self._require_identity()
                        existing_config = _get_tracker_email_config(user)
                        for secret_id in {
                            str(existing_config.get("password_secret_id") or "").strip(),
                            str(existing_config.get("access_token_secret_id") or "").strip(),
                            str(existing_config.get("refresh_token_secret_id") or "").strip(),
                        }:
                            if not secret_id:
                                continue
                            try:
                                application.delete_secret(secret_id)
                            except KeyError:
                                pass
                        refreshed_user = _clear_tracker_email_config(application, user)
                        self._send_json(
                            {
                                "deleted": "tracker_email_integration",
                                "integration": _tracker_email_integration_payload(application, refreshed_user),
                            },
                            status=HTTPStatus.OK,
                        )
                        return

    if segments[:1] == ["tracker"] and len(segments) == 2:
                        user, _ = self._require_identity()
                        if segments[1].startswith("external_"):
                            _, deleted_external = _delete_external_tracker_application(
                                application,
                                user,
                                segments[1],
                            )
                            self._send_json(
                                {
                                    "deleted": deleted_external["review_id"],
                                    "application_id": deleted_external["application_id"],
                                },
                                status=HTTPStatus.OK,
                            )
                            return
                        review = application.get_review(segments[1])
                        run = application.get_run(review.run_id)
                        if not application.user_can_access_workspace(user, run.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        application.delete_job(review.run_id, review.job_id)
                        self._send_json(
                            {
                                "deleted": review.review_id,
                                "run_id": review.run_id,
                                "job_id": review.job_id,
                            },
                            status=HTTPStatus.OK,
                        )
                        return

    return False
