# ruff: noqa: F821
from __future__ import annotations

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.api.routes.route_support import bind_server_globals

# Workspaces, workspace builder, templates, runs, run resources, and workers.
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
    registry.prefix('GET', ('workspaces',), _handle_get, auth_required=True, name='workspace.workspaces')
    registry.prefix('GET', ('workspace-builder',), _handle_get, auth_required=True, name='workspace.builder')
    registry.prefix('GET', ('workflow-templates',), _handle_get, auth_required=True, name='workspace.templates')
    registry.prefix('GET', ('connectors',), _handle_get, auth_required=True, name='workspace.connectors')
    registry.prefix('GET', ('generations',), _handle_get, auth_required=True, name='workspace.generations')
    registry.prefix('GET', ('renderers',), _handle_get, auth_required=True, name='workspace.renderers')
    registry.prefix('GET', ('runs',), _handle_get, auth_required=True, name='workspace.runs')
    registry.prefix('GET', ('review-queue',), _handle_get, auth_required=True, name='workspace.review_queue')
    registry.prefix('GET', ('artifacts',), _handle_get, auth_required=True, name='workspace.artifacts')
    registry.prefix('GET', ('workers',), _handle_get, auth_required=True, name='workspace.workers')
    registry.prefix('POST', ('career-url-discovery',), _handle_post, auth_required=True, name='workspace.career_url_discovery')
    registry.prefix('POST', ('workspaces',), _handle_post, auth_required=True, name='workspace.workspaces.post')
    registry.prefix('POST', ('quick-apply',), _handle_post, auth_required=True, name='workspace.quick_apply')
    registry.prefix('POST', ('workspace-builder',), _handle_post, auth_required=True, name='workspace.builder.post')
    registry.prefix('POST', ('workflow-templates',), _handle_post, auth_required=True, name='workspace.templates.post')
    registry.prefix('POST', ('runs',), _handle_post, auth_required=True, name='workspace.runs.post')
    registry.prefix('POST', ('workers',), _handle_post, auth_required=True, name='workspace.workers.post')
    registry.prefix('PUT', ('workspace-builder',), _handle_put, auth_required=True, name='workspace.builder.put')
    registry.prefix('PUT', ('workspaces',), _handle_put, auth_required=True, name='workspace.workspaces.put')
    registry.prefix('PUT', ('workflow-templates',), _handle_put, auth_required=True, name='workspace.templates.put')
    registry.prefix('PUT', ('runs',), _handle_put, auth_required=True, name='workspace.runs.put')
    registry.prefix('DELETE', ('workspaces',), _handle_delete, auth_required=True, name='workspace.workspaces.delete')
    registry.prefix('DELETE', ('workflow-templates',), _handle_delete, auth_required=True, name='workspace.templates.delete')
    registry.prefix('DELETE', ('runs',), _handle_delete, auth_required=True, name='workspace.runs.delete')


def _handle_get(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["workspaces"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_READ)
                        limit = _parse_int_param(query, "limit", default=50, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        workspaces = self._authorized_workspaces(user)
                        paged_workspaces = workspaces[offset : offset + limit]
                        self._send_json(
                            {
                                "workspaces": [_workspace_summary(item) for item in paged_workspaces],
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_workspaces)),
                            }
                        )
                        return

    if segments[:1] == ["workspaces"] and len(segments) == 2:
                        self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_READ)
                        self._send_json(application.get_workspace(segments[1]).to_dict())
                        return

    if segments == ["workspace-builder", "catalog"]:
                        self._require_scope(TOKEN_SCOPE_WORKSPACES_READ)
                        self._send_json(application.get_workspace_builder_catalog())
                        return

    if segments == ["workflow-templates"]:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                        limit = _parse_int_param(query, "limit", default=50, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        templates = application.list_workflow_templates()
                        paged_templates = templates[offset : offset + limit]
                        self._send_json(
                            {
                                "workflow_templates": [_workflow_template_summary(item) for item in paged_templates],
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_templates)),
                            }
                        )
                        return

    if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                        self._send_json(application.get_workflow_template(segments[1]).to_dict())
                        return

    if segments == ["connectors"]:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                        self._send_json({"connectors": [_component_summary(item) for item in application.list_connectors()]})
                        return

    if segments == ["generations"]:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                        self._send_json({"generations": [_component_summary(item) for item in application.list_generations()]})
                        return

    if segments == ["renderers"]:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                        self._send_json({"renderers": [_component_summary(item) for item in application.list_renderers()]})
                        return

    if segments == ["runs"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_RUNS_READ)
                        limit = _parse_int_param(query, "limit", default=50, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        status = str((query.get("status") or [""])[0])
                        workspace_id = str((query.get("workspace_id") or [""])[0])
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        workspaces = {workspace.id: workspace for workspace in self._authorized_workspaces(user)}
                        runs = self._authorized_runs(user, limit=limit, offset=offset, status=status, workspace_id=workspace_id)
                        self._send_json(
                            {
                                "runs": [
                                    {
                                        **_run_summary(item),
                                        "workspace_name": (
                                            workspaces[item.workspace_id].name
                                            if item.workspace_id in workspaces
                                            else item.workspace_id
                                        ),
                                    }
                                    for item in runs
                                ],
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(runs)),
                            }
                        )
                        return

    if segments == ["review-queue"]:
                        user, _ = self._require_identity()
                        limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                        run_id = str((query.get("run_id") or [""])[0]).strip()
                        status = str((query.get("status") or [""])[0]).strip().lower()
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        entries = _collect_review_queue_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                        if status:
                            entries = [item for item in entries if str(item.get("status") or "").lower() == status]
                        paged_entries = entries[offset : offset + limit]
                        self._send_json(
                            {
                                "items": paged_entries,
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                            }
                        )
                        return

    if segments == ["artifacts"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                        limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                        run_id = str((query.get("run_id") or [""])[0]).strip()
                        artifact_type = str((query.get("artifact_type") or [""])[0]).strip().lower()
                        if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        entries = _collect_artifact_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                        if artifact_type:
                            entries = [item for item in entries if str(item.get("artifact_type") or "").lower() == artifact_type]
                        paged_entries = entries[offset : offset + limit]
                        self._send_json(
                            {
                                "artifacts": paged_entries,
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                            }
                        )
                        return

    if segments[:1] == ["runs"] and len(segments) == 2:
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_READ)
                        payload = run.to_dict()
                        payload["capped_sites"] = list(
                            application.repositories.job_store.load_blob(run.id, "capped_sites", []) or []
                        )
                        self._send_json(payload)
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "customer-view":
                        request_started = perf_counter()
                        timings_ms: dict[str, float] = {}
                        run = None
                        payload = None
                        outcome = "success"
                        try:
                            phase_started = perf_counter()
                            user, _ = self._require_identity()
                            timings_ms["auth"] = round((perf_counter() - phase_started) * 1000, 2)

                            phase_started = perf_counter()
                            run = application.get_run(segments[1])
                            timings_ms["run_load"] = round((perf_counter() - phase_started) * 1000, 2)

                            phase_started = perf_counter()
                            if not application.user_can_access_run(user, run):
                                raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                            timings_ms["access_check"] = round((perf_counter() - phase_started) * 1000, 2)

                            phase_started = perf_counter()
                            payload = _collect_run_customer_view(application, user, run)
                            timings_ms["payload_build"] = round((perf_counter() - phase_started) * 1000, 2)

                            phase_started = perf_counter()
                            self._send_json(payload)
                            timings_ms["send_json_call"] = round((perf_counter() - phase_started) * 1000, 2)
                            return
                        except Exception as exc:
                            outcome = type(exc).__name__
                            raise
                        finally:
                            timings_ms["total"] = round((perf_counter() - request_started) * 1000, 2)
                            run_payload = payload.get("run") if isinstance(payload, dict) and isinstance(payload.get("run"), dict) else {}
                            summary = payload.get("summary") if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
                            stages = payload.get("stages") if isinstance(payload, dict) and isinstance(payload.get("stages"), list) else []
                            review = payload.get("review") if isinstance(payload, dict) and isinstance(payload.get("review"), dict) else {}
                            logging.getLogger("backend.api.customer_view").info(
                                json.dumps(
                                    {
                                        "event": "customer_view_timing",
                                        "outcome": outcome,
                                        "run_id": str(segments[1] or ""),
                                        "workspace_id": str(getattr(run, "workspace_id", "") or ""),
                                        "run_status": str(run_payload.get("status") or getattr(run, "status", "") or ""),
                                        "timings_ms": timings_ms,
                                        "counts": {
                                            "stages": len(stages),
                                            "included_jobs": int(summary.get("included_job_count") or 0),
                                            "excluded_jobs": int(summary.get("excluded_job_count") or 0),
                                            "generated_jobs": int(summary.get("generated_job_count") or 0),
                                            "review_included_jobs": int(review.get("included_count") or 0),
                                            "review_excluded_jobs": int(review.get("excluded_count") or 0),
                                        },
                                        "client_disconnected": bool(getattr(self, "_client_disconnected", False)),
                                    },
                                    separators=(",", ":"),
                                )
                            )

    if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "jobs" and segments[3] == "by-id":
                        user, _ = self._require_identity()
                        run = application.get_run(segments[1])
                        if not application.user_can_access_run(user, run):
                            raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                        self._send_json(
                            application.get_job_workspace(
                                user_id=user.user_id,
                                run_id=segments[1],
                                job_id=segments[4],
                            ),
                            status=HTTPStatus.OK,
                        )
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "jobs":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_READ)
                        job_sets = application.list_job_sets(segments[1])
                        self._send_json({"run_id": segments[1], "job_sets": {key: [job.to_dict() for job in jobs] for key, jobs in job_sets.items()}})
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_READ)
                        jobs = application.get_job_set(segments[1], segments[3])
                        self._send_json({"run_id": segments[1], "set_key": segments[3], "jobs": [job.to_dict() for job in jobs]})
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "artifacts":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                        artifacts = application.list_artifacts(segments[1])
                        self._send_json({"run_id": segments[1], "artifacts": [artifact.to_dict() for artifact in artifacts]})
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                        self._send_json(application.get_artifact(segments[1], segments[3]).to_dict())
                        return

    if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "artifacts" and segments[4] == "download":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                        document_id = _document_id_for_artifact(segments[1], segments[3])
                        document = _find_document_entry(application, self._require_identity()[0], document_id)
                        _assert_document_export_allowed(
                            document,
                            export_anyway=_parse_bool_param(query, "export_anyway"),
                        )
                        file_path, download_name = _resolve_artifact_download(application, segments[1], segments[3])
                        self._send_file(file_path, download_name=download_name)
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "reviews":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_REVIEWS_READ)
                        limit = _parse_int_param(query, "limit", default=100, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        reviews = application.list_reviews(run_id=segments[1], limit=limit, offset=offset)
                        self._send_json(
                            {
                                "run_id": segments[1],
                                "reviews": [review.to_dict() for review in reviews],
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(reviews)),
                            }
                        )
                        return

    if segments == ["workers"]:
                        self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                        limit = _parse_int_param(query, "limit", default=50, maximum=500)
                        offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                        status = str((query.get("status") or [""])[0]).strip()
                        workers = application.list_workers(limit=limit, offset=offset, status=status)
                        self._send_json(
                            {
                                "workers": [worker.to_dict() for worker in workers],
                                "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(workers)),
                            }
                        )
                        return

    if segments[:1] == ["workers"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                        self._send_json(application.get_worker(segments[1]).to_dict())
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                        review = application.get_review(segments[3])
                        run = application.get_run(review.run_id)
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_REVIEWS_READ)
                        if review.run_id != segments[1]:
                            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Review not found for run.")
                            return
                        self._send_json(review.to_dict())
                        return

    return False


def _handle_post(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    payload = self._read_json_body()

    if segments == ["career-url-discovery", "run"]:
                        self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                        source = str(payload.get("source") or "regular").strip().lower()
                        if source not in {"regular", "phd", "all"}:
                            raise ValueError("Choose regular companies, universities/PhD, or all sources.")
                        raw_limit = payload.get("limit")
                        limit = 25 if raw_limit in {None, ""} else int(raw_limit)
                        limit = max(0, min(5000, limit))
                        offset = max(0, int(payload.get("offset") or 0))
                        discovery_args = SimpleNamespace(
                            source=source,
                            input=str(payload.get("input") or ""),
                            input_format="auto",
                            company_name_column="",
                            homepage_url_column="",
                            homepage_url="",
                            domain="",
                            company_name="",
                            limit=limit,
                            offset=offset,
                            timeout_seconds=max(5, min(60, int(payload.get("timeout_seconds") or 20))),
                            shallow_crawl_pages=max(0, min(20, int(payload.get("shallow_crawl_pages") or 8))),
                            use_rendered_fallback=bool(payload.get("use_rendered_fallback") or False),
                            allow_domain_guessing=False,
                            output_json=str(payload.get("output_json") or ""),
                            output_company_sites=str(payload.get("output_company_sites") or ""),
                            save_mysql=bool(payload.get("save_mysql") or False),
                            mysql_host=str(payload.get("mysql_host") or ""),
                            mysql_port=int(payload.get("mysql_port") or 0),
                            mysql_user=str(payload.get("mysql_user") or ""),
                            mysql_password=str(payload.get("mysql_password") or ""),
                            mysql_database=str(payload.get("mysql_database") or ""),
                            mysql_table=str(payload.get("mysql_table") or ""),
                        )
                        result = run_career_url_discovery(discovery_args)
                        compact_results = []
                        for item in result.get("results", []):
                            compact_results.append(
                                {
                                    "company_name": item.get("company_name", ""),
                                    "homepage_url": item.get("homepage_url", ""),
                                    "primary_career_url": item.get("primary_career_url", ""),
                                    "secondary_candidate_urls": item.get("secondary_candidate_urls", []),
                                    "ats_type": item.get("ats_type", ""),
                                    "confidence_score": item.get("confidence_score", 0),
                                    "crawl_status": item.get("crawl_status", ""),
                                    "validation_evidence": item.get("validation_evidence", []),
                                }
                            )
                        self._send_json(
                            {
                                "processed": result.get("processed", 0),
                                "found": result.get("found", 0),
                                "not_found": result.get("not_found", 0),
                                "saved_list_path": result.get("output_company_sites", ""),
                                "details_path": result.get("output_json", ""),
                                "company_site_entries": result.get("company_site_entries", 0),
                                "mysql_rows_saved": result.get("mysql_rows_saved", 0),
                                "results": compact_results,
                            },
                            status=HTTPStatus.OK,
                        )
                        return

    if segments == ["workspaces"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_WRITE)
                        workspace_id = str(payload.get("id") or "").strip()
                        existing_workspace = None
                        if workspace_id:
                            try:
                                existing_workspace = application.get_workspace(workspace_id)
                            except KeyError:
                                existing_workspace = None
                        if existing_workspace and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        payload["owner_user_id"] = (
                            existing_workspace.owner_user_id if existing_workspace else user.user_id
                        )
                        self._send_json(application.upsert_workspace(payload).to_dict(), status=HTTPStatus.CREATED)
                        return

    if segments == ["quick-apply", "runs"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                        context = self._auth_context()
                        workspace_id = str(payload.get("workspace_id") or "").strip()
                        if workspace_id:
                            if not application.user_can_access_workspace(user, workspace_id):
                                raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                            workspace = application.get_workspace(workspace_id)
                        else:
                            workspace = _ensure_quick_apply_workspace(application, user)
                            workspace_id = workspace.id
                        run_input_overrides = _build_quick_apply_run_input_overrides(
                            application,
                            user,
                            workspace,
                            payload,
                        )
                        check_and_increment_quota(
                            application,
                            user.user_id,
                            "runs_per_month",
                            context.plan_id,
                            route="/quick-apply/runs",
                            quota_overrides=context.quota_overrides,
                        )
                        execution_mode = str(payload.get("execution_mode") or "sync").strip().lower()
                        max_attempts = max(1, int(payload.get("max_attempts") or 1))
                        manual_urls = payload.get("manual_urls") or payload.get("urls") or []
                        if execution_mode == "queued":
                            run, invalid_entries = application.start_quick_apply_run(
                                workspace_id,
                                manual_urls=manual_urls,
                                run_input_overrides=run_input_overrides,
                                execute=False,
                                enqueue=True,
                                requested_by=f"api:{user.user_id}",
                                max_attempts=max_attempts,
                            )
                        elif execution_mode == "planned":
                            run, invalid_entries = application.start_quick_apply_run(
                                workspace_id,
                                manual_urls=manual_urls,
                                run_input_overrides=run_input_overrides,
                                execute=False,
                                enqueue=False,
                                requested_by=f"api:{user.user_id}",
                                max_attempts=max_attempts,
                            )
                        elif execution_mode == "sync":
                            run, invalid_entries = application.start_quick_apply_run(
                                workspace_id,
                                manual_urls=manual_urls,
                                run_input_overrides=run_input_overrides,
                                execute=True,
                                enqueue=False,
                                requested_by=f"api:{user.user_id}",
                                max_attempts=max_attempts,
                            )
                        else:
                            raise ValueError("execution_mode must be one of: queued, planned, sync")
                        self._send_json(
                            {
                                "run": run.to_dict(),
                                "accepted_url_count": int(run.metadata.get("accepted_url_count") or 0),
                                "invalid_entries": invalid_entries,
                            },
                            status=HTTPStatus.CREATED,
                        )
                        return

    if segments == ["workspace-builder", "workspaces"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_WRITE)
                        context = self._auth_context()
                        check_and_increment_quota(
                            application,
                            user.user_id,
                            "workspaces",
                            context.plan_id,
                            route="/workspace-builder/workspaces",
                            quota_overrides=context.quota_overrides,
                        )
                        prepared_payload, runtime_settings = _prepare_workspace_builder_payload_with_cv(
                            application,
                            payload,
                            user,
                        )
                        workspace_id = str(
                            prepared_payload.get("workspace_id")
                            or _slugify(str(prepared_payload.get("name") or ""))
                        ).strip()
                        existing_workspace = None
                        if workspace_id:
                            try:
                                existing_workspace = application.get_workspace(workspace_id)
                            except KeyError:
                                existing_workspace = None
                        if existing_workspace and not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        prepared_payload["owner_user_id"] = (
                            existing_workspace.owner_user_id if existing_workspace else user.user_id
                        )
                        workspace = application.create_workspace_from_scratch(prepared_payload)
                        workspace = _persist_workspace_runtime_settings(application, workspace, runtime_settings)
                        self._send_json(workspace.to_dict(), status=HTTPStatus.CREATED)
                        return

    if segments == ["workspace-builder", "source-validation"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_READ)
                        context = self._auth_context()
                        validation = application.validate_workspace_builder_sources(
                            payload,
                            user_id=user.user_id,
                            plan_id=context.plan_id,
                            quota_overrides=context.quota_overrides,
                        )
                        workspace_id = str((payload or {}).get("workspace_id") or "").strip()
                        application.emit_event(
                            (
                                "workspace_source_validation_passed"
                                if validation.get("valid")
                                else "workspace_source_validation_failed"
                            ),
                            user_id=user.user_id,
                            workspace_id=workspace_id,
                            source="api",
                            route="/workspace-builder/source-validation",
                            payload={
                                "workspace_id": workspace_id,
                                "field_errors": list(validation.get("field_errors") or []),
                                "source_results": list(validation.get("source_results") or []),
                            },
                        )
                        self._send_json(validation, status=HTTPStatus.OK)
                        return

    if segments == ["workflow-templates"]:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                        self._send_json(application.upsert_workflow_template(payload).to_dict(), status=HTTPStatus.CREATED)
                        return

    if segments == ["runs"]:
                        user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                        context = self._auth_context()
                        workspace_id = str(payload.get("workspace_id") or "").strip()
                        if not workspace_id:
                            raise ValueError("workspace_id is required")
                        if not application.user_can_access_workspace(user, workspace_id):
                            raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                        check_and_increment_quota(
                            application,
                            user.user_id,
                            "runs_per_month",
                            context.plan_id,
                            route="/runs",
                            quota_overrides=context.quota_overrides,
                        )
                        workspace = application.get_workspace(workspace_id)
                        execution_mode = str(payload.get("execution_mode") or "queued").strip().lower()
                        max_attempts = max(1, int(payload.get("max_attempts") or 1))
                        run_input_overrides = _build_run_input_overrides(
                            user,
                            payload,
                            workspace_settings=workspace.settings,
                        )
                        if _builder_workspace_flow_id(workspace):
                            validation = application.validate_workspace_builder_sources(
                                {
                                    "workspace_id": workspace.id,
                                    "flow_id": _builder_workspace_flow_id(workspace),
                                    "source_ids": _builder_workspace_source_ids(workspace),
                                    "settings": dict(workspace.settings or {}),
                                },
                                user_id=user.user_id,
                                plan_id=context.plan_id,
                                quota_overrides=context.quota_overrides,
                            )
                            if not validation.get("valid"):
                                raise BackendValidationError(
                                    "run_preflight_failed",
                                    "Run blocked until the workspace source setup is fixed.",
                                    details={
                                        "phase": "run_preflight",
                                        "workspace_id": workspace.id,
                                        "flow_id": _builder_workspace_flow_id(workspace),
                                        "source_ids": _builder_workspace_source_ids(workspace),
                                        "module_ids": [
                                            str(item).strip()
                                            for item in (workspace.metadata or {}).get("modules") or []
                                            if str(item).strip()
                                        ],
                                        "field_errors": list(validation.get("field_errors") or []),
                                        "source_results": list(validation.get("source_results") or []),
                                    },
                                )
                            run_input_overrides = {
                                **dict(validation.get("policy_run_overrides") or {}),
                                **run_input_overrides,
                            }
                        if execution_mode == "queued":
                            run = application.enqueue_run(
                                workspace_id,
                                run_input_overrides=run_input_overrides,
                                requested_by=f"api:{user.user_id}",
                                max_attempts=max_attempts,
                            )
                        elif execution_mode == "planned":
                            run = application.start_run(
                                workspace_id,
                                run_input_overrides=run_input_overrides,
                                execute=False,
                                requested_by=f"api:{user.user_id}",
                                max_attempts=max_attempts,
                            )
                        elif execution_mode == "sync":
                            run = application.start_run(
                                workspace_id,
                                run_input_overrides=run_input_overrides,
                                execute=True,
                                requested_by=f"api:{user.user_id}",
                                max_attempts=max_attempts,
                            )
                        else:
                            raise ValueError("execution_mode must be one of: queued, planned, sync")
                        application.emit_event(
                            "run_started",
                            user_id=user.user_id,
                            workspace_id=workspace.id,
                            run_id=run.id,
                            source="api",
                            route="/runs",
                            automation_flow=_builder_workspace_flow_id(workspace) or "unknown",
                            source_ids=_builder_workspace_source_ids(workspace),
                            run_kind=str((run.metadata or {}).get("run_kind") or "standard"),
                        )
                        self._send_json(run.to_dict(), status=HTTPStatus.CREATED)
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "cancel":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                        self._send_json(application.cancel_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "retry":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                        self._send_json(application.retry_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "resume":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                        self._send_json(application.resume_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "reviews":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                        self._send_json(application.upsert_review(run_id=segments[1], payload=payload).to_dict(), status=HTTPStatus.CREATED)
                        return

    if segments == ["workers", "process-next"]:
                        self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                        worker_id = str(payload.get("worker_id") or "api_worker")
                        lease_seconds = max(5, int(payload.get("lease_seconds") or 60))
                        configure_worker_logging()
                        worker = WorkerService(
                            application=application,
                            worker_id=worker_id,
                            lease_seconds=lease_seconds,
                            logger=logging.getLogger("backend.worker.api"),
                        )
                        run = worker.process_next(auto_retry_failed=bool(payload.get("auto_retry_failed", True)))
                        if run is None:
                            self._send_json({"status": "idle"})
                            return
                        self._send_json({"status": "processed", "run": run.to_dict()}, status=HTTPStatus.OK)
                        return

    if segments == ["workers", "recover-stale"]:
                        self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                        recovered = application.recover_stale_workers()
                        self._send_json({"recovered_workers": [worker.to_dict() for worker in recovered]}, status=HTTPStatus.OK)
                        return

    return False


def _handle_put(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    payload = self._read_json_body()

    if segments[:2] == ["workspace-builder", "workspaces"] and len(segments) == 3:
                        user, _ = self._require_workspace_access(
                            workspace_id=segments[2],
                            required_scope=TOKEN_SCOPE_WORKSPACES_WRITE,
                        )
                        existing_workspace = application.get_workspace(segments[2])
                        prepared_payload, runtime_settings = _prepare_workspace_builder_payload_with_cv(
                            application,
                            payload,
                            user,
                            existing_workspace=existing_workspace,
                        )
                        prepared_payload["owner_user_id"] = existing_workspace.owner_user_id
                        workspace = application.update_workspace_from_scratch(segments[2], prepared_payload)
                        workspace = _persist_workspace_runtime_settings(application, workspace, runtime_settings)
                        self._send_json(workspace.to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["workspaces"] and len(segments) == 3 and segments[2] == "schedule":
                        self._require_workspace_access(
                            workspace_id=segments[1],
                            required_scope=TOKEN_SCOPE_WORKSPACES_WRITE,
                        )
                        workspace = application.update_workspace_schedule(segments[1], payload)
                        self._send_json(_workspace_summary(workspace), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["workspaces"] and len(segments) == 2:
                        self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_WRITE)
                        existing_workspace = application.get_workspace(segments[1])
                        payload["id"] = segments[1]
                        payload["owner_user_id"] = existing_workspace.owner_user_id
                        self._send_json(application.upsert_workspace(payload).to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                        payload["id"] = segments[1]
                        self._send_json(application.upsert_workflow_template(payload).to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                        jobs = payload.get("jobs")
                        if not isinstance(jobs, list):
                            raise ValueError("jobs must be a list")
                        job_set = application.upsert_job_set(segments[1], segments[3], jobs)
                        self._send_json({"run_id": segments[1], "set_key": segments[3], "jobs": [job.to_dict() for job in job_set]})
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_ARTIFACTS_WRITE)
                        payload["artifact_id"] = segments[3]
                        self._send_json(application.upsert_artifact(segments[1], payload).to_dict(), status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                        self._send_json(application.upsert_review(run_id=segments[1], payload=payload, review_id=segments[3]).to_dict(), status=HTTPStatus.OK)
                        return

    return False


def _handle_delete(context: ApiRouteContext) -> bool | None:
    _bind_server_globals()
    self = context.handler
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments[:1] == ["workspaces"] and len(segments) == 2:
                        self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_WRITE)
                        application.delete_workspace(segments[1])
                        self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                        self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                        application.delete_workflow_template(segments[1])
                        self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "jobs" and segments[3] == "by-id":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                        application.delete_job(segments[1], segments[4])
                        self._send_json({"deleted": segments[4], "run_id": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                        application.delete_job_set(segments[1], segments[3])
                        self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_ARTIFACTS_WRITE)
                        application.delete_artifact(segments[1], segments[3])
                        self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                        review = application.get_review(segments[3])
                        run = application.get_run(review.run_id)
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                        application.delete_review(segments[3])
                        self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                        return

    if segments[:1] == ["runs"] and len(segments) == 2:
                        run = application.get_run(segments[1])
                        self._require_run_access(run=run, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                        application.delete_run(segments[1])
                        self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                        return

    return False
