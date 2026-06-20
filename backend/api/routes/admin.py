# ruff: noqa: F821
from __future__ import annotations

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.api.routes.route_support import bind_server_globals

# Admin, billing, settings, analytics, users, secrets, and webhooks.
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
    registry.exact('GET', ('billing', 'plans'), _handle_get, auth_required=False, name='admin.billing.plans')
    registry.exact('GET', ('auth', 'me'), _handle_get, auth_required=True, name='admin.auth.me')
    registry.prefix('GET', ('billing',), _handle_get, auth_required=True, name='admin.billing')
    registry.prefix('GET', ('scrapeops',), _handle_get, auth_required=True, name='admin.scrapeops')
    registry.prefix('GET', ('analytics',), _handle_get, auth_required=True, name='admin.analytics')
    registry.prefix('GET', ('admin',), _handle_get, auth_required=True, name='admin.admin')
    registry.prefix('GET', ('dev',), _handle_get, auth_required=True, name='admin.dev')
    registry.exact('GET', ('dashboard',), _handle_get, auth_required=True, name='admin.dashboard')
    registry.exact('GET', ('settings',), _handle_get, auth_required=True, name='admin.settings')
    registry.prefix('GET', ('users',), _handle_get, auth_required=True, name='admin.users')
    registry.exact('GET', ('tokens',), _handle_get, auth_required=True, name='admin.tokens')
    registry.prefix('GET', ('secrets',), _handle_get, auth_required=True, name='admin.secrets')
    registry.exact('POST', ('webhooks', 'clerk'), _handle_post, auth_required=False, name='admin.webhooks.clerk')
    registry.exact('POST', ('webhooks', 'creem'), _handle_post, auth_required=False, name='admin.webhooks.creem')
    registry.prefix('POST', ('admin',), _handle_post, auth_required=True, name='admin.admin.post')
    registry.prefix('POST', ('analytics',), _handle_post, auth_required=True, name='admin.analytics.post')
    registry.prefix('POST', ('billing',), _handle_post, auth_required=True, name='admin.billing.post')
    registry.prefix('POST', ('users',), _handle_post, auth_required=True, name='admin.users.post')
    registry.prefix('POST', ('secrets',), _handle_post, auth_required=True, name='admin.secrets.post')
    registry.prefix('PUT', ('admin',), _handle_put, auth_required=True, name='admin.admin.put')
    registry.exact('PUT', ('settings',), _handle_put, auth_required=True, name='admin.settings.put')
    registry.prefix('PUT', ('users',), _handle_put, auth_required=True, name='admin.users.put')
    registry.prefix('PUT', ('secrets',), _handle_put, auth_required=True, name='admin.secrets.put')
    registry.prefix('DELETE', ('users',), _handle_delete, auth_required=True, name='admin.users.delete')
    registry.prefix('DELETE', ('admin',), _handle_delete, auth_required=True, name='admin.admin.delete')
    registry.prefix('DELETE', ('secrets',), _handle_delete, auth_required=True, name='admin.secrets.delete')


def _handle_get(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["billing", "plans"]:
                        self._send_json({"plans": list_plans()})
                        return

    if segments == ["auth", "me"]:
                        context = self._auth_context()
                        user, token = context.user, context.token
                        token_payload = token.to_public_dict() if hasattr(token, "to_public_dict") else {
                            "user_id": user.user_id,
                            "scopes": list(getattr(token, "scopes", []) or []),
                            "auth_method": getattr(context, "auth_method", "unknown"),
                        }
                        self._send_json(
                            {
                                "user": _serialize_authenticated_user(
                                    application,
                                    user,
                                    auth_method=context.auth_method,
                                    clerk_user_id=context.clerk_user_id,
                                    role=context.role,
                                    plan_id=context.plan_id,
                                    quota_overrides=context.quota_overrides,
                                ),
                                "token": token_payload,
                            }
                        )
                        return

    if segments == ["billing", "subscription"]:
                        context = self._auth_context()
                        self._send_json(
                            _subscription_response_payload(
                                application,
                                user_id=context.user.user_id,
                                plan_id=context.plan_id,
                                quota_overrides=context.quota_overrides,
                            )
                        )
                        return

    if segments == ["scrapeops", "usage"]:
                        context = self._auth_context()
                        occurred_from = str((query.get("occurred_from") or [""])[0]).strip()
                        occurred_to = str((query.get("occurred_to") or [""])[0]).strip()
                        self._send_json(
                            application.get_scrapeops_user_usage_summary(
                                user_id=context.user.user_id,
                                plan_id=context.plan_id,
                                quota_overrides=context.quota_overrides,
                            )
                            | {
                                "usage": application.get_scrapeops_usage_summary(
                                    user_id=context.user.user_id,
                                    occurred_from=occurred_from,
                                    occurred_to=occurred_to,
                                )
                            }
                        )
                        return

    if segments == ["analytics", "overview"]:
                        user, _ = self._require_identity()
                        if str(user.role or "").strip().lower() != ROLE_ADMIN:
                            raise PermissionError("Admin access required.")
                        self._send_json(application.get_analytics_overview())
                        return

    if segments == ["admin", "scrapeops", "usage"]:
                        self._require_admin()
                        occurred_from = str((query.get("occurred_from") or [""])[0]).strip()
                        occurred_to = str((query.get("occurred_to") or [""])[0]).strip()
                        workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                        run_id = str((query.get("run_id") or [""])[0]).strip()
                        user_id = str((query.get("user_id") or [""])[0]).strip()
                        self._send_json(
                            application.get_scrapeops_admin_dashboard(
                                user_id=user_id,
                                workspace_id=workspace_id,
                                run_id=run_id,
                                occurred_from=occurred_from,
                                occurred_to=occurred_to,
                                date=str((query.get("date") or [""])[0]).strip(),
                            )
                        )
                        return

    if segments == ["admin", "scrapeops", "policy"]:
                        self._require_admin()
                        self._send_json(application.get_scrapeops_admin_policy())
                        return

    if segments == ["admin", "analytics", "snapshot"]:
                        self._require_admin()
                        self._send_json(_build_admin_analytics_snapshot(application))
                        return

    if segments == ["admin", "events"]:
                        self._require_admin()
                        limit = _parse_int_param(query, "limit", default=50, maximum=200)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        event_name = str((query.get("event_name") or [""])[0]).strip()
                        user_id = str((query.get("user_id") or [""])[0]).strip()
                        occurred_from = str((query.get("occurred_from") or [""])[0]).strip()
                        occurred_to = str((query.get("occurred_to") or [""])[0]).strip()
                        events_payload = application.list_analytics_events(
                            limit=limit,
                            offset=offset,
                            event_name=event_name,
                            user_id=user_id,
                            occurred_from=occurred_from,
                            occurred_to=occurred_to,
                        )
                        self._send_json(
                            {
                                "events": events_payload["events"],
                                "meta": {
                                    **self._pagination_meta(
                                        limit=limit,
                                        offset=offset,
                                        returned=len(events_payload["events"]),
                                    ),
                                    "total": int(events_payload["total"]),
                                },
                            }
                        )
                        return

    if segments == ["admin", "promo-codes"]:
                        self._require_admin()
                        limit = _parse_int_param(query, "limit", default=50, maximum=200)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        self._send_json(_list_admin_promo_codes(limit=limit, offset=offset))
                        return

    if segments == ["admin", "users", "health"]:
                        self._require_admin()
                        self._send_json(_build_admin_user_health_snapshot(application))
                        return

    if segments == ["dev", "bootstrap-auth"]:
                        user = application.upsert_user(
                            {
                                "email": "admin@runr.local",
                                "display_name": "Runr Admin",
                                "role": "admin",
                                "allowed_workspace_ids": [],
                            }
                        )
                        token, raw_token = application.issue_api_token(
                            user_id=user.user_id,
                            name="frontend-dev",
                            scopes=[],
                        )
                        self._send_json(
                            {
                                "api_base_url": self._request_api_prefix() or "/v1",
                                "access_token": raw_token,
                                "user": user.to_dict(),
                                "token": token.to_public_dict(),
                            }
                        )
                        return

    if segments == ["dashboard"]:
                        user, _ = self._require_identity()
                        self._send_json(_dashboard_payload(application, user))
                        return

    if segments == ["settings"]:
                        user, _ = self._require_identity()
                        self._send_json(_build_settings_payload(application, user))
                        return

    if segments == ["users"]:
                        self._require_scope(TOKEN_SCOPE_USERS_READ)
                        limit = _parse_int_param(query, "limit", default=50, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        users = application.list_users()
                        paged_users = users[offset : offset + limit]
                        self._send_json(
                            {
                                "users": [user.to_dict() for user in paged_users],
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_users)),
                            }
                        )
                        return

    if segments[:1] == ["users"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_USERS_READ)
                        self._send_json(application.get_user(segments[1]).to_dict())
                        return

    if segments[:1] == ["users"] and len(segments) == 3 and segments[2] == "tokens":
                        self._require_scope(TOKEN_SCOPE_USERS_READ)
                        limit = _parse_int_param(query, "limit", default=100, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        tokens = [
                            token.to_public_dict()
                            for token in application.list_api_tokens(
                                user_id=segments[1],
                                include_inactive=True,
                                limit=limit,
                                offset=offset,
                            )
                        ]
                        self._send_json(
                            {
                                "user_id": segments[1],
                                "tokens": tokens,
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(tokens)),
                            }
                        )
                        return

    if segments == ["tokens"]:
                        self._require_scope(TOKEN_SCOPE_USERS_READ)
                        user_id = str((query.get("user_id") or [""])[0]).strip()
                        include_inactive = str((query.get("include_inactive") or ["false"])[0]).strip().lower() in {"1", "true", "yes"}
                        limit = _parse_int_param(query, "limit", default=100, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        tokens = [
                            token.to_public_dict()
                            for token in application.list_api_tokens(
                                user_id=user_id,
                                include_inactive=include_inactive,
                                limit=limit,
                                offset=offset,
                            )
                        ]
                        self._send_json(
                            {
                                "tokens": tokens,
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(tokens)),
                            }
                        )
                        return

    if segments == ["secrets"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_READ)
                        workspace_id = str((query.get("workspace_id") or [""])[0])
                        limit = _parse_int_param(query, "limit", default=100, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        secrets = [
                            secret.to_public_dict()
                            for secret in application.list_secrets(workspace_id=workspace_id, limit=limit, offset=offset)
                        ]
                        self._send_json(
                            {
                                "secrets": secrets,
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(secrets)),
                            }
                        )
                        return

    if segments[:1] == ["secrets"] and len(segments) == 2:
                        user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_READ)
                        secret = application.get_secret(segments[1])
                        if secret.workspace_id and not application.user_can_access_workspace(user, secret.workspace_id):
                            raise PermissionError(f"Workspace access denied for '{secret.workspace_id}'.")
                        self._send_json(secret.to_public_dict())
                        return

    return False


def _handle_post(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["webhooks", "clerk"]:
                        event_payload = verify_clerk_webhook(self._read_raw_body(), self.headers)
                        self._send_json(_handle_clerk_webhook_event(application, event_payload), status=HTTPStatus.OK)
                        return

    if segments == ["webhooks", "creem"]:
                        raw_body = self._read_raw_body()
                        verify_creem_webhook_signature(raw_body, self.headers.get("creem-signature", ""))
                        webhook_payload = json.loads(raw_body.decode("utf-8") or "{}")
                        if not isinstance(webhook_payload, dict):
                            raise ValueError("Creem webhook body must be a JSON object.")
                        event_name = str(webhook_payload.get("eventType") or webhook_payload.get("event_type") or "").strip()
                        if not event_name:
                            raise ValueError("Creem webhook payload is missing eventType.")
                        self._send_json(
                            _handle_creem_webhook_event(
                                application,
                                event_name=event_name,
                                payload=webhook_payload,
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    payload = self._read_json_body()

    if segments == ["admin", "scrapeops", "reconciliation", "run"]:
                        self._require_admin()
                        self._send_json(
                            application.run_scrapeops_reconciliation_cycle(force=True, source="admin"),
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["analytics", "events"]:
                        context = self._auth_context()
                        event_name = str(payload.get("event_name") or "").strip()
                        if not event_name:
                            raise ValueError("event_name is required")
                        route_value = str(payload.get("route") or payload.get("page") or "").strip()
                        event_payload = dict(payload.get("payload") or {})
                        for key, value in payload.items():
                            if key in {"event_name", "payload", "route", "source"}:
                                continue
                            event_payload[key] = value
                        application.emit_event(
                            event_name,
                            user_id=context.user.user_id,
                            session_id=context.session_id,
                            route=route_value,
                            source=str(payload.get("source") or "frontend").strip(),
                            payload=event_payload,
                        )
                        self._send_json({"status": "ok", "event_name": event_name}, status=HTTPStatus.ACCEPTED)
                        return

    if segments == ["admin", "promo-codes"]:
                        admin_user, _ = self._require_admin()
                        promo_code_payload = _create_admin_promo_code(payload)
                        application.emit_event(
                            "promo_code_created",
                            user_id=admin_user.user_id,
                            route="/admin/promo-codes",
                            source="api",
                            payload={
                                "discount_id": promo_code_payload["discount_id"],
                                "discount": promo_code_payload["discount"],
                                "expires_at": promo_code_payload["expires_at"],
                            },
                        )
                        self._send_json({"promo_code": promo_code_payload}, status=HTTPStatus.CREATED)
                        return

    if segments == ["billing", "checkout"]:
                        context = self._auth_context()
                        target_plan_id = normalize_plan_id(payload.get("plan_id") or DEFAULT_PLAN_ID)
                        if target_plan_id == DEFAULT_PLAN_ID:
                            raise ValueError("Checkout is only available for paid plans.")
                        plan = get_plan(target_plan_id)
                        product_id = str(plan.get("creem_product_id") or "").strip()
                        if not product_id:
                            raise ValueError(f"Creem product id is not configured for plan '{target_plan_id}'.")
                        source_page = str(payload.get("source_page") or payload.get("sourcePage") or "").strip()
                        promo_code = str(payload.get("promo_code") or payload.get("promoCode") or "").strip().upper()
                        if promo_code:
                            promo_code = _normalize_promo_code(promo_code)
                        checkout_url = get_creem_checkout_url(
                            context.user.user_id,
                            product_id,
                            context.user.email,
                            name=context.user.display_name,
                            discount_code=promo_code,
                            custom_data={
                                "plan_id": target_plan_id,
                                "source_page": source_page,
                                "clerk_user_id": context.clerk_user_id,
                            },
                            redirect_url=f"{self._frontend_origin()}/pricing?checkout=success&plan_id={target_plan_id}",
                        )
                        application.emit_event(
                            "checkout_started",
                            user_id=context.user.user_id,
                            session_id=context.session_id,
                            route="/billing/checkout",
                            source="api",
                            payload={
                                "user_id": context.user.user_id,
                                "target_plan_id": target_plan_id,
                                "current_plan_id": context.plan_id,
                                "source_page": source_page,
                                "promo_code_present": bool(promo_code),
                            },
                        )
                        self._send_json({"checkout_url": checkout_url}, status=HTTPStatus.OK)
                        return

    if segments == ["billing", "portal"]:
                        context = self._auth_context()
                        subscription_record = _lookup_subscription_record(application, context.user.user_id) or {}
                        portal_url = get_creem_customer_portal_url(
                            subscription_id=str(subscription_record.get("creem_subscription_id") or "").strip(),
                            customer_id=str(subscription_record.get("creem_customer_id") or "").strip(),
                        )
                        self._send_json({"portal_url": portal_url}, status=HTTPStatus.OK)
                        return

    if segments == ["users"]:
                        self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                        self._send_json(application.upsert_user(payload).to_dict(), status=HTTPStatus.CREATED)
                        return

    if segments[:1] == ["users"] and len(segments) == 3 and segments[2] == "tokens":
                        self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                        token, raw_token = application.issue_api_token(
                            user_id=segments[1],
                            name=str(payload.get("name") or "api-token"),
                            scopes=[str(item) for item in payload.get("scopes") or [] if str(item).strip()],
                            expires_at=str(payload.get("expires_at") or ""),
                            metadata=dict(payload.get("metadata") or {}),
                        )
                        self._send_json({"token": token.to_public_dict(), "access_token": raw_token}, status=HTTPStatus.CREATED)
                        return

    if segments == ["secrets"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                        workspace_id = str(payload.get("workspace_id") or "")
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        self._send_json(application.upsert_secret(payload).to_public_dict(), status=HTTPStatus.CREATED)
                        return

    return False


def _handle_put(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    payload = self._read_json_body()

    if segments == ["admin", "scrapeops", "policy"]:
                        self._require_admin()
                        self._send_json(application.save_scrapeops_admin_policy(payload), status=HTTPStatus.OK)
                        return

    if segments == ["settings"]:
                        user, _ = self._require_identity()
                        metadata = dict(user.metadata or {})
                        existing_profile = dict(metadata.get("profile") or {})
                        existing_documents = dict(metadata.get("documents") or {})

                        if "profile" in payload:
                            profile_payload = dict(payload.get("profile") or {})
                            metadata["profile"] = _merge_profile_metadata(existing_profile, profile_payload, user)

                        if "defaults" in payload:
                            defaults_payload = dict(payload.get("defaults") or {})
                            default_workspace_id = str(defaults_payload.get("default_workspace_id") or "")
                            if default_workspace_id and not application.user_can_access_workspace(user, default_workspace_id):
                                raise PermissionError(f"Workspace access denied for '{default_workspace_id}'.")
                            metadata["defaults"] = {
                                "default_workspace_id": default_workspace_id,
                                "default_execution_mode": str(defaults_payload.get("default_execution_mode") or "queued"),
                                "default_profile_id": str(defaults_payload.get("default_profile_id") or ""),
                                "default_prompt_set_id": str(defaults_payload.get("default_prompt_set_id") or ""),
                                "max_jobs_per_run": max(1, int(defaults_payload.get("max_jobs_per_run") or 25)),
                            }

                        if "documents" in payload:
                            documents_payload = dict(payload.get("documents") or {})
                            metadata["documents"] = _merge_document_metadata(existing_documents, documents_payload)

                        if "review_preferences" in payload:
                            review_payload = dict(payload.get("review_preferences") or {})
                            metadata["review_preferences"] = {
                                "require_review_before_use": bool(review_payload.get("require_review_before_use", True)),
                                "default_decision_state": str(review_payload.get("default_decision_state") or "waiting_review"),
                                "rejection_note_required": bool(review_payload.get("rejection_note_required", True)),
                                "auto_open_next_item": bool(review_payload.get("auto_open_next_item", True)),
                            }

                        if "account" in payload:
                            account_payload = dict(payload.get("account") or {})
                            user.display_name = str(account_payload.get("display_name") or user.display_name)
                            user.email = str(account_payload.get("email") or user.email)

                        user.metadata = metadata
                        user.updated_at = datetime.now(timezone.utc).isoformat()
                        application.repositories.auth_repository.upsert_user(user)
                        refreshed_user = application.get_user(user.user_id)
                        self._send_json(_build_settings_payload(application, refreshed_user), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["users"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                        payload["user_id"] = segments[1]
                        self._send_json(application.upsert_user(payload).to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["secrets"] and len(segments) == 2:
                        user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                        payload["secret_id"] = segments[1]
                        workspace_id = str(payload.get("workspace_id") or "")
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        self._send_json(application.upsert_secret(payload).to_public_dict(), status=HTTPStatus.OK)
                        return

    return False


def _handle_delete(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments[:1] == ["users"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                        application.delete_user(segments[1])
                        self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments[:2] == ["admin", "promo-codes"] and len(segments) == 3:
                        admin_user, _ = self._require_admin()
                        delete_creem_discount(segments[2])
                        application.emit_event(
                            "promo_code_deleted",
                            user_id=admin_user.user_id,
                            route="/admin/promo-codes",
                            source="api",
                            payload={"discount_id": segments[2]},
                        )
                        self._send_json({"deleted": segments[2]}, status=HTTPStatus.OK)
                        return

    if segments[:1] == ["users"] and len(segments) == 4 and segments[2] == "tokens":
                        self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                        self._send_json(application.revoke_api_token(segments[3]).to_public_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["secrets"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                        application.delete_secret(segments[1])
                        self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                        return

    return False
