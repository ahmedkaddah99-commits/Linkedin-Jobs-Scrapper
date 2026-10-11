from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "backend").is_dir() and (candidate / "user_config").is_dir():
            return candidate
    return Path.cwd().resolve()


REPO_ROOT = find_repo_root(Path(__file__).parent)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def emit(check: str, status: str, **detail: Any) -> None:
    print(json.dumps({"check": check, "status": status, **detail}, sort_keys=True, default=str))


def load_env(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def missing(check: str, keys: list[str]) -> bool:
    absent = [key for key in keys if not os.getenv(key, "").strip()]
    if absent:
        emit(check, "FAILED", detail="missing env: " + ", ".join(absent))
        return True
    emit(f"{check}.env", "OK", keys=len(keys))
    return False


def http_json(method: str, url: str, *, headers: dict[str, str] | None = None, payload: Any = None, timeout: int = 30):
    request_headers = {"Accept": "application/json", "User-Agent": "runr-production-debug/1.0"}
    if headers:
        request_headers.update(headers)
    encoded = None
    if payload is not None:
        encoded = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=encoded, headers=request_headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return json.loads(body or "{}")


def http_text(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    max_bytes: int = 4096,
) -> tuple[int, str]:
    request_headers = {"Accept": "*/*", "User-Agent": "runr-production-debug/1.0"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(max_bytes).decode("utf-8", errors="replace")
        return int(getattr(response, "status", 0) or response.getcode()), body


def safe_http_error(exc: urllib.error.HTTPError) -> str:
    return f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}"


def _render_log_message(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("message") or item.get("text") or item.get("log") or item)
    return str(item)


def _parse_json_log_payload(message: str) -> dict[str, Any] | None:
    start = str(message or "").find("{")
    if start < 0:
        return None
    candidate = message[start:].strip()
    try:
        payload = json.loads(candidate)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _summarize_api_timing_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_route: dict[str, dict[str, Any]] = {}
    slowest: list[dict[str, Any]] = []
    for event in events:
        route = str(event.get("route") or "unknown")
        bucket = by_route.setdefault(
            route,
            {"count": 0, "disconnected": 0, "max_duration_ms": 0.0, "total_duration_ms": 0.0},
        )
        duration = float(event.get("duration_ms") or 0)
        bucket["count"] += 1
        bucket["total_duration_ms"] += duration
        bucket["max_duration_ms"] = max(float(bucket["max_duration_ms"]), duration)
        if event.get("client_disconnected"):
            bucket["disconnected"] += 1
        slowest.append(
            {
                "route": route,
                "route_name": str(event.get("route_name") or ""),
                "status": event.get("status"),
                "duration_ms": duration,
                "client_disconnected": bool(event.get("client_disconnected")),
                "error_type": str(event.get("error_type") or ""),
            }
        )
    routes = []
    for route, bucket in by_route.items():
        count = int(bucket["count"])
        routes.append(
            {
                "route": route,
                "count": count,
                "disconnected": int(bucket["disconnected"]),
                "avg_duration_ms": round(float(bucket["total_duration_ms"]) / max(count, 1), 2),
                "max_duration_ms": round(float(bucket["max_duration_ms"]), 2),
            }
        )
    return {
        "count": len(events),
        "routes": sorted(routes, key=lambda item: (-float(item["max_duration_ms"]), item["route"]))[:10],
        "slowest": sorted(slowest, key=lambda item: -float(item["duration_ms"]))[:10],
    }


def _summarize_customer_view_events(events: list[dict[str, Any]], *, run_id: str = "") -> dict[str, Any]:
    filtered = [
        event
        for event in events
        if not run_id or str(event.get("run_id") or "") == run_id
    ]
    rows = []
    for event in filtered:
        timings = event.get("timings_ms") if isinstance(event.get("timings_ms"), dict) else {}
        rows.append(
            {
                "run_id": str(event.get("run_id") or ""),
                "workspace_id": str(event.get("workspace_id") or ""),
                "outcome": str(event.get("outcome") or ""),
                "run_status": str(event.get("run_status") or ""),
                "total_ms": float(timings.get("total") or 0),
                "payload_build_ms": float(timings.get("payload_build") or 0),
                "client_disconnected": bool(event.get("client_disconnected")),
                "counts": event.get("counts") if isinstance(event.get("counts"), dict) else {},
            }
        )
    return {
        "count": len(filtered),
        "slowest": sorted(rows, key=lambda item: -float(item["total_ms"]))[:10],
    }


def _summarize_customer_view_payload_events(events: list[dict[str, Any]], *, run_id: str = "") -> dict[str, Any]:
    filtered = [
        event
        for event in events
        if not run_id or str(event.get("run_id") or "") == run_id
    ]
    rows = []
    for event in filtered:
        timings = event.get("timings_ms") if isinstance(event.get("timings_ms"), dict) else {}
        phase_rows = [
            {"phase": str(key), "duration_ms": float(value or 0)}
            for key, value in timings.items()
            if str(key) != "total"
        ]
        rows.append(
            {
                "run_id": str(event.get("run_id") or ""),
                "workspace_id": str(event.get("workspace_id") or ""),
                "run_status": str(event.get("run_status") or ""),
                "total_ms": float(timings.get("total") or sum(item["duration_ms"] for item in phase_rows)),
                "slowest_phases": sorted(phase_rows, key=lambda item: -float(item["duration_ms"]))[:8],
                "counts": event.get("counts") if isinstance(event.get("counts"), dict) else {},
            }
        )
    return {
        "count": len(filtered),
        "slowest": sorted(rows, key=lambda item: -float(item["total_ms"]))[:10],
    }


def _summarize_auth_timing_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_outcome: dict[str, dict[str, Any]] = {}
    slowest: list[dict[str, Any]] = []
    for event in events:
        outcome_key = "::".join(
            [
                str(event.get("token_shape") or "unknown"),
                str(event.get("auth_method") or "unknown"),
                str(event.get("outcome") or "unknown"),
            ]
        )
        bucket = by_outcome.setdefault(
            outcome_key,
            {"count": 0, "max_duration_ms": 0.0, "total_duration_ms": 0.0, "fallback_attempted": 0},
        )
        duration = float(event.get("duration_ms") or 0)
        bucket["count"] += 1
        bucket["total_duration_ms"] += duration
        bucket["max_duration_ms"] = max(float(bucket["max_duration_ms"]), duration)
        if event.get("fallback_attempted"):
            bucket["fallback_attempted"] += 1
        slowest.append(
            {
                "token_shape": str(event.get("token_shape") or ""),
                "auth_method": str(event.get("auth_method") or ""),
                "outcome": str(event.get("outcome") or ""),
                "duration_ms": duration,
                "fallback_attempted": bool(event.get("fallback_attempted")),
                "error_type": str(event.get("error_type") or ""),
            }
        )
    groups = []
    for key, bucket in by_outcome.items():
        token_shape, auth_method, outcome = key.split("::", 2)
        count = int(bucket["count"])
        groups.append(
            {
                "token_shape": token_shape,
                "auth_method": auth_method,
                "outcome": outcome,
                "count": count,
                "fallback_attempted": int(bucket["fallback_attempted"]),
                "avg_duration_ms": round(float(bucket["total_duration_ms"]) / max(count, 1), 2),
                "max_duration_ms": round(float(bucket["max_duration_ms"]), 2),
            }
        )
    return {
        "count": len(events),
        "groups": sorted(groups, key=lambda item: (-float(item["max_duration_ms"]), item["auth_method"]))[:10],
        "slowest": sorted(slowest, key=lambda item: -float(item["duration_ms"]))[:10],
    }


def _safe_json_object(raw_value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(raw_value or "{}"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_json_list(raw_value: Any) -> list[Any]:
    try:
        payload = json.loads(str(raw_value or "[]"))
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def _hash_value(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def _object_key_summary(key: str) -> dict[str, Any]:
    value = str(key or "").strip()
    prefix = value.split("/", 1)[0] if "/" in value else ""
    suffix = Path(value).suffix.lower()[:12]
    return {"key_hash": _hash_value(value), "prefix": prefix, "suffix": suffix}


def check_render(*, log_start: str = "", log_end: str = "", run_id: str = "") -> None:
    if missing("render", ["RENDER_API_KEY"]):
        return
    token = os.environ["RENDER_API_KEY"].strip()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        payload = http_json("GET", "https://api.render.com/v1/services?limit=20", headers=headers)
        raw_services = payload if isinstance(payload, list) else payload.get("services") or payload.get("data") or []
        services = []
        for item in raw_services:
            service = item.get("service") if isinstance(item, dict) and isinstance(item.get("service"), dict) else item
            if isinstance(service, dict):
                service_details = service.get("serviceDetails") or service.get("service_details") or {}
                if not isinstance(service_details, dict):
                    service_details = {}
                services.append(
                    {
                        "name": service.get("name"),
                        "id": service.get("id"),
                        "type": service.get("type"),
                        "owner_id": service.get("ownerId") or (service.get("owner") or {}).get("id"),
                        "health_check_path": service_details.get("healthCheckPath")
                        or service_details.get("health_check_path")
                        or "",
                    }
                )
        emit("render.services", "OK", count=len(services), services=services[:10])
    except urllib.error.HTTPError as exc:
        emit("render.services", "FAILED", detail=safe_http_error(exc))
        return
    except Exception as exc:
        emit("render.services", "FAILED", detail=str(exc)[:500])
        return

    owner_id = next((item.get("owner_id") for item in services if item.get("owner_id")), "")
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=2)
    start_value = log_start or start.isoformat().replace("+00:00", "Z")
    end_value = log_end or end.isoformat().replace("+00:00", "Z")
    for service in services:
        service_name = str(service.get("name") or "unknown")
        service_id = str(service.get("id") or "")
        if service_name in {"runr-api", "runr-worker", "runr-frontend"} and service_id:
            try:
                deploy_payload = http_json(
                    "GET",
                    f"https://api.render.com/v1/services/{service_id}/deploys?limit=1",
                    headers=headers,
                )
                raw_deploys = deploy_payload if isinstance(deploy_payload, list) else deploy_payload.get("deploys") or deploy_payload.get("data") or []
                deploy_item = raw_deploys[0] if raw_deploys else {}
                deploy = deploy_item.get("deploy") if isinstance(deploy_item, dict) and isinstance(deploy_item.get("deploy"), dict) else deploy_item
                deploy = deploy if isinstance(deploy, dict) else {}
                emit(
                    f"render.deploy.{service_name}",
                    "OK",
                    id=deploy.get("id"),
                    deploy_status=deploy.get("status"),
                    commit=deploy.get("commit", {}).get("id") if isinstance(deploy.get("commit"), dict) else deploy.get("commitId"),
                    created_at=deploy.get("createdAt") or deploy.get("created_at"),
                    finished_at=deploy.get("finishedAt") or deploy.get("finished_at"),
                    updated_at=deploy.get("updatedAt") or deploy.get("updated_at"),
                )
            except urllib.error.HTTPError as exc:
                emit(f"render.deploy.{service_name}", "FAILED", detail=safe_http_error(exc))
            except Exception as exc:
                emit(f"render.deploy.{service_name}", "FAILED", detail=str(exc)[:500])
        if service.get("name") not in {"runr-api", "runr-worker"}:
            continue
        if not owner_id or not service.get("id"):
            emit(f"render.logs.{service.get('name')}", "FAILED", detail="missing ownerId or service id")
            continue
        query = urllib.parse.urlencode(
            {
                "ownerId": owner_id,
                "resource": service["id"],
                "startTime": start_value,
                "endTime": end_value,
                "limit": "300",
            }
        )
        try:
            logs = http_json("GET", f"https://api.render.com/v1/logs?{query}", headers=headers)
            items = logs.get("logs") or logs.get("data") or logs.get("items") or ([] if not isinstance(logs, list) else logs)
            emit(
                f"render.logs.{service.get('name')}",
                "OK",
                count=len(items),
                has_more=logs.get("hasMore") if isinstance(logs, dict) else None,
                start=start_value,
                end=end_value,
            )
            if service.get("name") == "runr-api":
                parsed_payloads = [
                    payload
                    for payload in (_parse_json_log_payload(_render_log_message(item)) for item in items)
                    if payload is not None
                ]
                api_timings = [payload for payload in parsed_payloads if payload.get("event") == "api_request_timing"]
                customer_timings = [payload for payload in parsed_payloads if payload.get("event") == "customer_view_timing"]
                customer_payload_timings = [payload for payload in parsed_payloads if payload.get("event") == "customer_view_payload_timing"]
                auth_timings = [payload for payload in parsed_payloads if payload.get("event") == "auth_resolution_timing"]
                disconnects = [
                    _render_log_message(item)
                    for item in items
                    if "client_disconnect" in _render_log_message(item)
                ]
                emit("render.logs.runr-api.request_timing", "OK", **_summarize_api_timing_events(api_timings))
                emit("render.logs.runr-api.auth_timing", "OK", **_summarize_auth_timing_events(auth_timings))
                emit(
                    "render.logs.runr-api.customer_view_timing",
                    "OK",
                    run_id=run_id,
                    **_summarize_customer_view_events(customer_timings, run_id=run_id),
                )
                emit(
                    "render.logs.runr-api.customer_view_payload_timing",
                    "OK",
                    run_id=run_id,
                    **_summarize_customer_view_payload_events(customer_payload_timings, run_id=run_id),
                )
                emit(
                    "render.logs.runr-api.client_disconnects",
                    "OK",
                    count=len(disconnects),
                    sample_routes=sorted(
                        {
                            match.group(1)
                            for line in disconnects
                            for match in [re.search(r"route=([^ ]+)", line)]
                            if match
                        }
                    )[:10],
                )
        except urllib.error.HTTPError as exc:
            emit(f"render.logs.{service.get('name')}", "FAILED", detail=safe_http_error(exc))
        except Exception as exc:
            emit(f"render.logs.{service.get('name')}", "FAILED", detail=str(exc)[:500])


def _table_names(connection: Any) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute("select name from sqlite_master where type='table' order by name").fetchall()
    }


def _table_columns(connection: Any, table: str) -> set[str]:
    try:
        return {str(row["name"]) for row in connection.execute(f"pragma table_info({table})").fetchall()}
    except Exception:
        return set()


def _count_rows(connection: Any, table: str, run_id: str) -> int:
    return int(connection.execute(f"select count(*) as c from {table} where run_id=?", (run_id,)).fetchone()["c"])


def check_turso(*, run_id: str = "") -> dict[str, Any]:
    if missing("turso", ["TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"]):
        return {"object_keys": []}
    object_keys: list[str] = []
    try:
        from backend.database.connection import connect_database

        start = time.perf_counter()
        connection = connect_database(REPO_ROOT / "user_data" / "runr.sqlite3")
        try:
            tables = _table_names(connection)
            latest = None
            run_count = None
            if "runs" in tables:
                run_count = connection.execute("select count(*) as c from runs").fetchone()["c"]
                row = connection.execute("select id, workspace_id, status, created_at, finished_at, last_error from runs order by created_at desc limit 1").fetchone()
                latest = dict(row) if row else None
            frontend_diagnostics = []
            if "analytics_events" in tables:
                diagnostic_rows = connection.execute(
                    """
                    SELECT event_name, occurred_at, route, source, payload_json
                    FROM analytics_events
                    WHERE event_name IN ('frontend_api_request_failed', 'frontend_api_request_slow')
                    ORDER BY occurred_at DESC
                    LIMIT 20
                    """
                ).fetchall()
                for diagnostic_row in diagnostic_rows:
                    payload = _safe_json_object(diagnostic_row["payload_json"])
                    frontend_diagnostics.append(
                        {
                            "event_name": diagnostic_row["event_name"],
                            "occurred_at": diagnostic_row["occurred_at"],
                            "route": diagnostic_row["route"],
                            "source": diagnostic_row["source"],
                            "status": payload.get("status"),
                            "duration_ms": payload.get("duration_ms"),
                            "timeout_ms": payload.get("timeout_ms"),
                            "error_name": payload.get("error_name"),
                            "error_code": payload.get("error_code"),
                            "aborted": payload.get("aborted"),
                        }
                    )
            if run_id and "runs" in tables:
                run_rows = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT id, workspace_id, workflow_template_id, status, created_at, queued_at,
                               started_at, finished_at, updated_at, current_stage_id,
                               substr(coalesce(last_error,''),1,240) AS last_error,
                               attempt_count, max_attempts
                        FROM runs
                        WHERE id=?
                        """,
                        (run_id,),
                    ).fetchall()
                ]
                emit("turso.run_detail", "OK", run_id=run_id, count=len(run_rows), rows=run_rows[:1])

                if "run_stage_results" in tables:
                    stage_rows = [
                        dict(row)
                        for row in connection.execute(
                            """
                            SELECT sequence_no, stage_id, stage_type, status, started_at, finished_at,
                                   substr(coalesce(error,''),1,240) AS error,
                                   metrics_json, artifact_ids_json
                            FROM run_stage_results
                            WHERE run_id=?
                            ORDER BY sequence_no, stage_id
                            """,
                            (run_id,),
                        ).fetchall()
                    ]
                    summarized_stages = []
                    for row in stage_rows:
                        metrics = _safe_json_object(row.get("metrics_json"))
                        artifact_ids = _safe_json_list(row.get("artifact_ids_json"))
                        summarized_stages.append(
                            {
                                "sequence_no": row.get("sequence_no"),
                                "stage_id": row.get("stage_id"),
                                "stage_type": row.get("stage_type"),
                                "status": row.get("status"),
                                "started_at": row.get("started_at"),
                                "finished_at": row.get("finished_at"),
                                "error": row.get("error"),
                                "metric_keys": sorted(metrics.keys())[:12],
                                "artifact_id_count": len(artifact_ids),
                            }
                        )
                    emit("turso.run_stage_results", "OK", run_id=run_id, count=len(summarized_stages), rows=summarized_stages[:20])

                if "run_job_sets" in tables:
                    set_rows = [
                        dict(row)
                        for row in connection.execute(
                            """
                            SELECT set_key, length(coalesce(payload_json,'')) AS payload_bytes, updated_at
                            FROM run_job_sets
                            WHERE run_id=?
                            ORDER BY set_key
                            """,
                            (run_id,),
                        ).fetchall()
                    ]
                    emit("turso.run_job_sets", "OK", run_id=run_id, count=len(set_rows), rows=set_rows[:20])

                if "run_jobs" in tables:
                    job_count = _count_rows(connection, "run_jobs", run_id)
                    job_filter_rows = [
                        dict(row)
                        for row in connection.execute(
                            """
                            SELECT set_key, coalesce(filter_status,'') AS filter_status, count(*) AS count
                            FROM run_jobs
                            WHERE run_id=?
                            GROUP BY set_key, coalesce(filter_status,'')
                            ORDER BY set_key, filter_status
                            """,
                            (run_id,),
                        ).fetchall()
                    ]
                    emit("turso.run_jobs", "OK", run_id=run_id, count=job_count, groups=job_filter_rows[:30])

                if "artifacts" in tables:
                    artifact_rows = [
                        dict(row)
                        for row in connection.execute(
                            """
                            SELECT artifact_id, artifact_type, path, metadata_json, created_at
                            FROM artifacts
                            WHERE run_id=?
                            ORDER BY created_at, artifact_id
                            """,
                            (run_id,),
                        ).fetchall()
                    ]
                    artifact_groups: dict[str, int] = {}
                    artifact_summaries = []
                    for row in artifact_rows:
                        artifact_type = str(row.get("artifact_type") or "")
                        artifact_groups[artifact_type] = artifact_groups.get(artifact_type, 0) + 1
                        metadata = _safe_json_object(row.get("metadata_json"))
                        for key_name in ("object_key", "s3_key", "r2_key"):
                            key_value = str(metadata.get(key_name) or "").strip()
                            if key_value:
                                object_keys.append(key_value)
                        path_value = str(row.get("path") or "")
                        artifact_summaries.append(
                            {
                                "artifact_id_hash": _hash_value(str(row.get("artifact_id") or "")),
                                "artifact_type": artifact_type,
                                "path_suffix": Path(path_value).suffix.lower()[:12],
                                "path_is_absolute": bool(path_value.startswith("/") or re.match(r"^[A-Za-z]:", path_value)),
                                "metadata_keys": sorted(metadata.keys())[:12],
                                "created_at": row.get("created_at"),
                            }
                        )
                    emit(
                        "turso.run_artifacts",
                        "OK",
                        run_id=run_id,
                        count=len(artifact_rows),
                        groups=artifact_groups,
                        rows=artifact_summaries[:30],
                    )

                if "reviews" in tables:
                    review_columns = _table_columns(connection, "reviews")
                    status_expr = "coalesce(status,'')" if "status" in review_columns else "''"
                    review_rows = [
                        dict(row)
                        for row in connection.execute(
                            f"""
                            SELECT {status_expr} AS status, count(*) AS count
                            FROM reviews
                            WHERE run_id=?
                            GROUP BY {status_expr}
                            ORDER BY status
                            """,
                            (run_id,),
                        ).fetchall()
                    ]
                    emit("turso.reviews", "OK", run_id=run_id, count=_count_rows(connection, "reviews", run_id), groups=review_rows)

                if "run_document_bindings" in tables:
                    binding_rows = [
                        dict(row)
                        for row in connection.execute(
                            """
                            SELECT binding_key, document_id, asset_id, object_key, updated_at
                            FROM run_document_bindings
                            WHERE run_id=?
                            ORDER BY binding_key
                            """,
                            (run_id,),
                        ).fetchall()
                    ]
                    binding_summaries = []
                    for row in binding_rows:
                        object_key = str(row.get("object_key") or "").strip()
                        if object_key:
                            object_keys.append(object_key)
                        binding_summaries.append(
                            {
                                "binding_key": row.get("binding_key"),
                                "document_id_hash": _hash_value(str(row.get("document_id") or "")),
                                "asset_id_hash": _hash_value(str(row.get("asset_id") or "")),
                                "has_object_key": bool(object_key),
                                "object_key": _object_key_summary(object_key) if object_key else None,
                                "updated_at": row.get("updated_at"),
                            }
                        )
                    emit("turso.run_document_bindings", "OK", run_id=run_id, count=len(binding_rows), rows=binding_summaries[:30])
        finally:
            connection.close()
        emit("turso.query", "OK", tables_count=len(tables), runs=run_count, latest_run=latest, elapsed_ms=round((time.perf_counter() - start) * 1000))
        emit("turso.frontend_request_diagnostics", "OK", count=len(frontend_diagnostics), latest=frontend_diagnostics[:10])
    except Exception as exc:
        emit("turso.query", "FAILED", detail=str(exc)[:700])
    return {"object_keys": sorted(set(object_keys))}


def check_r2(skip_write: bool, *, object_keys: list[str] | None = None) -> None:
    if missing("r2", ["S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]):
        return
    try:
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
            region_name=os.getenv("S3_REGION") or "auto",
        )
        if skip_write:
            emit("r2.write_read_delete", "SKIPPED", detail="--skip-r2-write")
        else:
            start = time.perf_counter()
            key = "diagnostics/codex-production-debug.txt"
            s3.put_object(Bucket=os.environ["S3_BUCKET"], Key=key, Body=b"ok", ContentType="text/plain")
            body = s3.get_object(Bucket=os.environ["S3_BUCKET"], Key=key)["Body"].read()
            s3.delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)
            emit("r2.write_read_delete", "OK", bytes=len(body), elapsed_ms=round((time.perf_counter() - start) * 1000))
        keys = [str(key or "").strip() for key in (object_keys or []) if str(key or "").strip()]
        if not keys:
            emit("r2.object_heads", "SKIPPED", detail="no run object keys discovered")
            return
        head_results = []
        for key in keys[:50]:
            summary = _object_key_summary(key)
            try:
                response = s3.head_object(Bucket=os.environ["S3_BUCKET"], Key=key)
                head_results.append(
                    {
                        **summary,
                        "exists": True,
                        "bytes": int(response.get("ContentLength") or 0),
                        "content_type": str(response.get("ContentType") or ""),
                    }
                )
            except Exception as exc:
                head_results.append({**summary, "exists": False, "error_type": type(exc).__name__})
        emit(
            "r2.object_heads",
            "OK",
            checked=len(head_results),
            exists=sum(1 for item in head_results if item.get("exists")),
            missing=sum(1 for item in head_results if not item.get("exists")),
            objects=head_results[:20],
        )
    except Exception as exc:
        emit("r2.write_read_delete", "FAILED", detail=str(exc)[:700])


def check_clerk() -> None:
    if missing("clerk", ["CLERK_SECRET_KEY", "CLERK_PUBLISHABLE_KEY", "CLERK_WEBHOOK_SECRET"]):
        return
    try:
        from backend.integrations.clerk import _configured_clerk_issuer, _fetch_jwks

        issuer = _configured_clerk_issuer()
        keys = _fetch_jwks(issuer, force=True)
        emit("clerk.jwks", "OK", issuer_host=urllib.parse.urlparse(issuer).netloc, key_count=len(keys))
    except Exception as exc:
        emit("clerk.jwks", "FAILED", detail=str(exc)[:700])
    try:
        payload = http_json(
            "GET",
            "https://api.clerk.com/v1/users?limit=1",
            headers={"Authorization": "Bearer " + os.environ["CLERK_SECRET_KEY"].strip()},
        )
        count = len(payload) if isinstance(payload, list) else len(payload.get("data") or [])
        emit("clerk.users", "OK", count=count)
    except urllib.error.HTTPError as exc:
        emit("clerk.users", "FAILED", detail=safe_http_error(exc))
    except Exception as exc:
        emit("clerk.users", "FAILED", detail=str(exc)[:700])


def check_scrapeops() -> None:
    if missing("scrapeops", ["SCRAPEOPS_API_KEY"]):
        return
    try:
        from backend.integrations.scrapeops import check_scrapeops_proxy_health, fetch_account_usage

        usage = fetch_account_usage(os.environ["SCRAPEOPS_API_KEY"], timeout_seconds=20)
        emit("scrapeops.usage", "OK", keys=sorted(list(usage.keys()))[:12])
        health = check_scrapeops_proxy_health(os.environ["SCRAPEOPS_API_KEY"], timeout_seconds=20)
        emit("scrapeops.proxy_health", "OK", healthy=health.get("healthy"), reason=health.get("reason"), credits_remaining=health.get("credits_remaining"))
    except Exception as exc:
        emit("scrapeops", "FAILED", detail=str(exc)[:700])


def check_deepseek() -> None:
    if missing("deepseek", ["DEEPSEEK_API_KEY"]):
        return
    try:
        payload = {
            "model": os.getenv("DEEPSEEK_STAGE4_MODEL") or "deepseek-chat",
            "messages": [{"role": "user", "content": "Return only OK."}],
            "max_tokens": 5,
            "temperature": 0,
        }
        start = time.perf_counter()
        response = http_json(
            "POST",
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"].strip()},
            payload=payload,
            timeout=30,
        )
        emit("deepseek.chat", "OK", model=response.get("model"), choices=len(response.get("choices") or []), elapsed_ms=round((time.perf_counter() - start) * 1000))
    except urllib.error.HTTPError as exc:
        emit("deepseek.chat", "FAILED", detail=safe_http_error(exc))
    except Exception as exc:
        emit("deepseek.chat", "FAILED", detail=str(exc)[:700])


def check_creem() -> None:
    keys = ["CREEM_API_KEY", "CREEM_WEBHOOK_SECRET", "CREEM_LAUNCH_PRODUCT_ID", "CREEM_MOMENTUM_PRODUCT_ID", "CREEM_SCALE_PRODUCT_ID"]
    if missing("creem", keys):
        return
    try:
        from backend.integrations.creem import _creem_api_base_url

        api_key = os.environ["CREEM_API_KEY"].strip()
        base = _creem_api_base_url(api_key)
        payload = http_json("GET", f"{base}/discounts/search", headers={"x-api-key": api_key})
        emit("creem.discounts", "OK", base_host=urllib.parse.urlparse(base).netloc, top_keys=sorted(payload.keys())[:8] if isinstance(payload, dict) else [])
    except urllib.error.HTTPError as exc:
        emit("creem.discounts", "FAILED", detail=safe_http_error(exc))
    except Exception as exc:
        emit("creem.discounts", "FAILED", detail=str(exc)[:700])


def check_google_oauth() -> None:
    if missing("google_oauth", ["TRACKER_GOOGLE_OAUTH_CLIENT_ID", "TRACKER_GOOGLE_OAUTH_CLIENT_SECRET", "TRACKER_GOOGLE_OAUTH_REDIRECT_URI"]):
        return
    emit("google_oauth.config", "OK", live_probe="not_possible_without_user_oauth_token")


def _absolute_url(origin: str, asset_path: str) -> str:
    value = str(asset_path or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return origin.rstrip("/") + value
    return origin.rstrip("/") + "/" + value.lstrip("/")


def _discover_frontend_api_base(origin: str, html: str) -> dict[str, Any]:
    asset_paths = []
    for match in re.finditer(r"""(?:src|href)=["']([^"']+)["']""", html or ""):
        if urllib.parse.urlparse(match.group(1)).path.endswith(".js"):
            asset_paths.append(match.group(1))
    for match in re.finditer(r"""["'](/?assets/[^"']+\.js(?:\?[^"']*)?)["']""", html or ""):
        asset_paths.append(match.group(1))
    candidates: set[str] = set()
    searched_assets = []
    for asset_path in list(dict.fromkeys(asset_paths))[:8]:
        asset_url = _absolute_url(origin, asset_path)
        searched_assets.append(urllib.parse.urlparse(asset_url).path)
        try:
            _, script = http_text("GET", asset_url, timeout=20, max_bytes=1_000_000)
        except Exception:
            continue
        for match in re.finditer(r"""https?://[^"'\\\s]+/v1""", script):
            candidate = match.group(0).rstrip("/")
            # Vite/minifier output can contain a template literal such as
            # ``https://${n}/v1``. It is code, not a concrete DNS target.
            if "${" in candidate or "}" in candidate or "<" in candidate or ">" in candidate:
                continue
            candidates.add(candidate)
        if '"/v1"' in script or "'/v1'" in script:
            candidates.add("/v1")
    sorted_candidates = sorted(candidates)
    preferred = next((candidate for candidate in sorted_candidates if candidate.startswith("https://")), "")
    return {
        "api_base": preferred or (sorted_candidates[0] if sorted_candidates else ""),
        "candidate_count": len(sorted_candidates),
        "searched_assets": searched_assets,
    }


def check_frontend_config() -> None:
    origin = str(os.getenv("APP_FRONTEND_ORIGIN") or os.getenv("FRONTEND_ORIGIN") or "").strip().rstrip("/")
    allowed_origins = str(os.getenv("BACKEND_ALLOWED_ORIGINS") or "").strip()
    if not origin:
        emit("frontend.origin", "FAILED", detail="missing APP_FRONTEND_ORIGIN/FRONTEND_ORIGIN")
        return
    emit(
        "frontend.config",
        "OK",
        origin_host=urllib.parse.urlparse(origin).netloc,
        allowed_origin_configured=origin in {item.strip().rstrip("/") for item in allowed_origins.split(",") if item.strip()},
    )
    html = ""
    try:
        status, html = http_text("GET", origin, timeout=20)
        emit("frontend.http", "OK", status_code=status, bytes_sampled=len(html), has_html="<html" in html.lower())
    except urllib.error.HTTPError as exc:
        emit("frontend.http", "FAILED", detail=safe_http_error(exc))
    except Exception as exc:
        emit("frontend.http", "FAILED", detail=str(exc)[:500])
    discovery = _discover_frontend_api_base(origin, html)
    api_base = str(discovery.get("api_base") or "").rstrip("/")
    if api_base:
        parsed_base = urllib.parse.urlparse(api_base if api_base.startswith("http") else origin + api_base)
        emit(
            "frontend.bundle_api_base",
            "OK",
            api_host=parsed_base.netloc,
            api_base_path=parsed_base.path,
            is_relative=not api_base.startswith("http"),
            candidate_count=discovery.get("candidate_count"),
            searched_assets=discovery.get("searched_assets"),
        )
    else:
        emit("frontend.bundle_api_base", "FAILED", detail="no API base found in sampled frontend bundle")
        api_base = "/v1"
    health_base = api_base if api_base.startswith("http") else origin.rstrip("/") + "/" + api_base.lstrip("/")
    try:
        payload = http_json("GET", f"{health_base}/health/live", timeout=20)
        emit("frontend.api_proxy_health", "OK", payload=payload if isinstance(payload, dict) else {})
    except urllib.error.HTTPError as exc:
        emit("frontend.api_proxy_health", "FAILED", detail=safe_http_error(exc))
    except Exception as exc:
        emit("frontend.api_proxy_health", "FAILED", detail=str(exc)[:500])


def main() -> int:
    parser = argparse.ArgumentParser(description="Redacted production access checks for Runr.")
    parser.add_argument("--env", default="user_config/.env", help="Path to backend env file.")
    parser.add_argument("--skip-r2-write", action="store_true", help="Do not perform the R2 write/read/delete probe.")
    parser.add_argument("--log-start", default="", help="Optional Render log start time, RFC3339/Zulu.")
    parser.add_argument("--log-end", default="", help="Optional Render log end time, RFC3339/Zulu.")
    parser.add_argument("--run-id", default="", help="Optional run id used to filter customer-view timing summaries.")
    args = parser.parse_args()

    load_env(Path(args.env))
    check_render(log_start=args.log_start, log_end=args.log_end, run_id=args.run_id)
    turso_detail = check_turso(run_id=args.run_id)
    check_r2(skip_write=bool(args.skip_r2_write), object_keys=list(turso_detail.get("object_keys") or []))
    check_clerk()
    check_scrapeops()
    check_deepseek()
    check_creem()
    check_google_oauth()
    check_frontend_config()
    gemini_keys = [key for key in os.environ if "GEMINI" in key.upper() or "GOOGLE_GENAI" in key.upper()]
    emit("gemini.removed", "OK", configured_keys=len(gemini_keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
