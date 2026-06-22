from __future__ import annotations

import argparse
import json
import os
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


def safe_http_error(exc: urllib.error.HTTPError) -> str:
    return f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}"


def check_render() -> None:
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
                services.append(
                    {
                        "name": service.get("name"),
                        "id": service.get("id"),
                        "type": service.get("type"),
                        "owner_id": service.get("ownerId") or (service.get("owner") or {}).get("id"),
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
    for service in services:
        if service.get("name") not in {"runr-api", "runr-worker"}:
            continue
        if not owner_id or not service.get("id"):
            emit(f"render.logs.{service.get('name')}", "FAILED", detail="missing ownerId or service id")
            continue
        query = urllib.parse.urlencode(
            {
                "ownerId": owner_id,
                "resource": service["id"],
                "startTime": start.isoformat().replace("+00:00", "Z"),
                "endTime": end.isoformat().replace("+00:00", "Z"),
                "limit": "5",
            }
        )
        try:
            logs = http_json("GET", f"https://api.render.com/v1/logs?{query}", headers=headers)
            items = logs.get("logs") or logs.get("data") or logs.get("items") or ([] if not isinstance(logs, list) else logs)
            emit(f"render.logs.{service.get('name')}", "OK", count=len(items), has_more=logs.get("hasMore") if isinstance(logs, dict) else None)
        except urllib.error.HTTPError as exc:
            emit(f"render.logs.{service.get('name')}", "FAILED", detail=safe_http_error(exc))
        except Exception as exc:
            emit(f"render.logs.{service.get('name')}", "FAILED", detail=str(exc)[:500])


def check_turso() -> None:
    if missing("turso", ["TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"]):
        return
    try:
        from backend.database.connection import connect_database

        start = time.perf_counter()
        connection = connect_database(REPO_ROOT / "user_data" / "runr.sqlite3")
        try:
            tables = [row["name"] for row in connection.execute("select name from sqlite_master where type='table' order by name").fetchall()]
            latest = None
            run_count = None
            if "runs" in tables:
                run_count = connection.execute("select count(*) as c from runs").fetchone()["c"]
                row = connection.execute("select id, workspace_id, status, created_at, finished_at, last_error from runs order by created_at desc limit 1").fetchone()
                latest = dict(row) if row else None
        finally:
            connection.close()
        emit("turso.query", "OK", tables_count=len(tables), runs=run_count, latest_run=latest, elapsed_ms=round((time.perf_counter() - start) * 1000))
    except Exception as exc:
        emit("turso.query", "FAILED", detail=str(exc)[:700])


def check_r2(skip_write: bool) -> None:
    if missing("r2", ["S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]):
        return
    if skip_write:
        emit("r2.write_read_delete", "SKIPPED", detail="--skip-r2-write")
        return
    try:
        import boto3

        start = time.perf_counter()
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
            region_name=os.getenv("S3_REGION") or "auto",
        )
        key = "diagnostics/codex-production-debug.txt"
        s3.put_object(Bucket=os.environ["S3_BUCKET"], Key=key, Body=b"ok", ContentType="text/plain")
        body = s3.get_object(Bucket=os.environ["S3_BUCKET"], Key=key)["Body"].read()
        s3.delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)
        emit("r2.write_read_delete", "OK", bytes=len(body), elapsed_ms=round((time.perf_counter() - start) * 1000))
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Redacted production access checks for Runr.")
    parser.add_argument("--env", default="user_config/.env", help="Path to backend env file.")
    parser.add_argument("--skip-r2-write", action="store_true", help="Do not perform the R2 write/read/delete probe.")
    args = parser.parse_args()

    load_env(Path(args.env))
    check_render()
    check_turso()
    check_r2(skip_write=bool(args.skip_r2_write))
    check_clerk()
    check_scrapeops()
    check_deepseek()
    check_creem()
    check_google_oauth()
    gemini_keys = [key for key in os.environ if "GEMINI" in key.upper() or "GOOGLE_GENAI" in key.upper()]
    emit("gemini.removed", "OK", configured_keys=len(gemini_keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
