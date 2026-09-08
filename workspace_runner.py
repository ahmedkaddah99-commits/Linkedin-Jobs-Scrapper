import argparse
import json
import logging
import os
import socket
from uuid import uuid4

from backend.config import load_project_dotenv, validate_environment

load_project_dotenv()

from backend import create_backend
from backend.api import serve_api
from backend.security.redaction import public_run_summary, redact_sensitive_data
from backend.tools.discover_company_careers import (
    add_discover_company_careers_arguments,
    run_from_args as run_career_discovery_from_args,
)
from backend.worker import WorkerService, configure_worker_logging
from backend.worker.roles import WORKER_ROLES


def parse_key_value(items: list[str]) -> dict[str, str]:
    overrides: dict[str, object] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid override '{item}'. Use key=value.")
        key, value = item.split("=", 1)
        raw_value = value.strip()
        try:
            overrides[key.strip()] = json.loads(raw_value)
        except Exception:
            overrides[key.strip()] = raw_value
    return overrides


def _print_json(payload) -> None:
    print(json.dumps(redact_sensitive_data(payload), indent=2, ensure_ascii=True))


def _runtime_worker_id(
    configured_worker_id: str,
    *,
    default_prefix: str,
    runtime_environment: str | None = None,
    host_name: str | None = None,
    process_id: int | None = None,
) -> str:
    requested_worker_id = str(configured_worker_id or "").strip()
    if not requested_worker_id:
        return f"{default_prefix}_{uuid4().hex[:8]}"
    environment = str(
        runtime_environment if runtime_environment is not None else os.getenv("RUNR_ENV", "")
    ).strip().casefold()
    if environment not in {"prod", "production"}:
        return requested_worker_id
    instance_host = str(host_name if host_name is not None else socket.gethostname()).strip()
    if not instance_host:
        return requested_worker_id
    instance_suffix = f"_{instance_host}"
    if process_id is not None and int(process_id) > 0:
        instance_suffix += f"_{int(process_id)}"
    if requested_worker_id.endswith(instance_suffix):
        return requested_worker_id
    return f"{requested_worker_id}{instance_suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified workspace runner for job automation.")
    parser.add_argument("--data-dir", default=".backend_data")
    parser.add_argument("--storage", default="sqlite", choices=["sqlite", "file"])
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-workspaces", help="List seeded workspaces.")
    subparsers.add_parser("list-templates", help="List workflow templates.")
    subparsers.add_parser("list-connectors", help="List available connectors.")
    subparsers.add_parser("list-generations", help="List available generation strategies.")
    subparsers.add_parser("list-renderers", help="List available renderers.")
    subparsers.add_parser("list-users", help="List backend users.")
    discover_career_urls_parser = subparsers.add_parser(
        "discover-career-urls",
        help="Discover company career URLs from a CSV/JSON list.",
    )
    add_discover_company_careers_arguments(discover_career_urls_parser)
    list_workers_parser = subparsers.add_parser("list-workers", help="List worker heartbeats and leases.")
    list_workers_parser.add_argument("--limit", type=int, default=50)
    list_workers_parser.add_argument("--offset", type=int, default=0)
    list_workers_parser.add_argument("--status", default="")

    create_user_parser = subparsers.add_parser("create-user", help="Create or update a backend user.")
    create_user_parser.add_argument("--user-id", default="")
    create_user_parser.add_argument("--email", required=True)
    create_user_parser.add_argument("--display-name", default="")
    create_user_parser.add_argument("--role", default="viewer", choices=["admin", "editor", "reviewer", "viewer"])
    create_user_parser.add_argument("--workspace", nargs="*", default=[])

    list_tokens_parser = subparsers.add_parser("list-tokens", help="List API tokens for a user.")
    list_tokens_parser.add_argument("--user-id", required=True)
    list_tokens_parser.add_argument("--include-inactive", action="store_true")

    create_token_parser = subparsers.add_parser("create-token", help="Issue a bearer token for a user.")
    create_token_parser.add_argument("--user-id", required=True)
    create_token_parser.add_argument("--name", required=True)
    create_token_parser.add_argument("--scope", nargs="*", default=[])
    create_token_parser.add_argument("--expires-at", default="")

    bootstrap_auth_parser = subparsers.add_parser(
        "bootstrap-dev-auth",
        help="Create/update an admin user and print a fresh access token for local frontend use.",
    )
    bootstrap_auth_parser.add_argument("--email", default="admin@runr.local")
    bootstrap_auth_parser.add_argument("--display-name", default="Runr Admin")
    bootstrap_auth_parser.add_argument("--token-name", default="frontend-dev")

    revoke_token_parser = subparsers.add_parser("revoke-token", help="Revoke an API token.")
    revoke_token_parser.add_argument("--token-id", required=True)

    list_secrets_parser = subparsers.add_parser("list-secrets", help="List backend secrets.")
    list_secrets_parser.add_argument("--workspace-id", default="")

    set_secret_parser = subparsers.add_parser("set-secret", help="Create or update a backend secret.")
    set_secret_parser.add_argument("--secret-id", default="")
    set_secret_parser.add_argument("--name", required=True)
    set_secret_parser.add_argument("--provider", default="stored", choices=["stored", "env"])
    set_secret_parser.add_argument("--workspace-id", default="")
    set_secret_parser.add_argument("--description", default="")
    set_secret_parser.add_argument("--env-var-name", default="")
    set_secret_parser.add_argument("--value", default="")

    delete_secret_parser = subparsers.add_parser("delete-secret", help="Delete a backend secret.")
    delete_secret_parser.add_argument("--secret-id", required=True)

    list_runs_parser = subparsers.add_parser("list-runs", help="List recent runs.")
    list_runs_parser.add_argument("--limit", type=int, default=50)
    list_runs_parser.add_argument("--status", default="")
    list_runs_parser.add_argument("--workspace-id", default="")

    run_parser = subparsers.add_parser("run", help="Execute, queue, or plan a workspace run.")
    run_parser.add_argument("--workspace", required=True)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--queue", action="store_true")
    run_parser.add_argument("--max-attempts", type=int, default=1)
    run_parser.add_argument("--override-json", default="")
    run_parser.add_argument("--set", nargs="*", default=[])

    cancel_parser = subparsers.add_parser("cancel-run", help="Cancel a queued or running run.")
    cancel_parser.add_argument("--run-id", required=True)

    retry_parser = subparsers.add_parser("retry-run", help="Retry a failed or cancelled run from scratch.")
    retry_parser.add_argument("--run-id", required=True)

    resume_parser = subparsers.add_parser("resume-run", help="Resume a planned, failed, or cancelled run.")
    resume_parser.add_argument("--run-id", required=True)

    process_next_parser = subparsers.add_parser("process-next", help="Process the next queued run.")
    process_next_parser.add_argument("--no-auto-retry", action="store_true")
    process_next_parser.add_argument("--worker-id", default="")
    process_next_parser.add_argument("--lease-seconds", type=int, default=60)
    process_next_parser.add_argument(
        "--worker-role",
        choices=WORKER_ROLES,
        default=os.getenv("RUNR_WORKER_ROLE", "customer"),
    )

    worker_parser = subparsers.add_parser("run-worker", help="Run a lease-aware polling worker service.")
    worker_parser.add_argument("--worker-id", default="")
    worker_parser.add_argument("--max-runs", type=int, default=0, help="0 means unlimited.")
    worker_parser.add_argument("--sleep-seconds", type=float, default=5.0)
    worker_parser.add_argument("--lease-seconds", type=int, default=60)
    worker_parser.add_argument("--no-auto-retry", action="store_true")
    worker_parser.add_argument(
        "--worker-role",
        choices=WORKER_ROLES,
        default=os.getenv("RUNR_WORKER_ROLE", "customer"),
    )

    serve_parser = subparsers.add_parser("serve-api", help="Start the minimal JSON API.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    validate_environment()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "serve-api":
        serve_api(host=args.host, port=args.port, data_dir=args.data_dir, storage_backend=args.storage)
        return 0

    application = create_backend(args.data_dir, storage_backend=args.storage)

    if args.command == "list-workspaces":
        for workspace in application.list_workspaces():
            print(f"{workspace.id}: {workspace.name} [{workspace.workflow_template_id}]")
        return 0

    if args.command == "list-templates":
        for template in application.list_workflow_templates():
            print(f"{template.id}: {template.name} ({len(template.stages)} stages)")
        return 0

    if args.command == "list-connectors":
        for descriptor in application.list_connectors():
            print(f"{descriptor.id}: {descriptor.name}")
        return 0

    if args.command == "list-generations":
        for descriptor in application.list_generations():
            print(f"{descriptor.id}: {descriptor.name}")
        return 0

    if args.command == "list-renderers":
        for descriptor in application.list_renderers():
            print(f"{descriptor.id}: {descriptor.name}")
        return 0

    if args.command == "discover-career-urls":
        return run_career_discovery_from_args(args)

    if args.command == "list-runs":
        for run in application.list_runs(limit=args.limit, status=args.status, workspace_id=args.workspace_id):
            print(f"{run.id} | {run.workspace_id} | {run.status} | attempts={run.attempt_count}/{run.max_attempts}")
        return 0

    if args.command == "list-users":
        for user in application.list_users():
            workspaces = ",".join(user.allowed_workspace_ids) if user.allowed_workspace_ids else "*"
            print(f"{user.user_id} | {user.email} | {user.role} | workspaces={workspaces}")
        return 0

    if args.command == "list-workers":
        workers = application.list_workers(limit=args.limit, offset=args.offset, status=args.status)
        _print_json([worker.to_dict() for worker in workers])
        return 0

    if args.command == "create-user":
        payload = {
            "user_id": args.user_id,
            "email": args.email,
            "display_name": args.display_name,
            "role": args.role,
            "allowed_workspace_ids": args.workspace,
        }
        user = application.upsert_user(payload)
        _print_json(user.to_dict())
        return 0

    if args.command == "list-tokens":
        tokens = application.list_api_tokens(user_id=args.user_id, include_inactive=args.include_inactive)
        _print_json([token.to_public_dict() for token in tokens])
        return 0

    if args.command == "create-token":
        token, raw_token = application.issue_api_token(
            user_id=args.user_id,
            name=args.name,
            scopes=args.scope,
            expires_at=args.expires_at,
        )
        _print_json({"token": token.to_public_dict(), "access_token": raw_token})
        return 0

    if args.command == "bootstrap-dev-auth":
        user = application.upsert_user(
            {
                "email": args.email,
                "display_name": args.display_name,
                "role": "admin",
                "allowed_workspace_ids": [],
            }
        )
        token, raw_token = application.issue_api_token(
            user_id=user.user_id,
            name=args.token_name,
            scopes=[],
        )
        _print_json(
            {
                "user": {
                    "user_id": user.user_id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                },
                "token": token.to_public_dict(),
                "access_token": raw_token,
                "api_base_url": "http://127.0.0.1:8000/v1",
            }
        )
        return 0

    if args.command == "revoke-token":
        token = application.revoke_api_token(args.token_id)
        _print_json(token.to_public_dict())
        return 0

    if args.command == "list-secrets":
        secrets = application.list_secrets(workspace_id=args.workspace_id)
        _print_json([secret.to_public_dict() for secret in secrets])
        return 0

    if args.command == "set-secret":
        payload = {
            "secret_id": args.secret_id,
            "name": args.name,
            "provider": args.provider,
            "workspace_id": args.workspace_id,
            "description": args.description,
            "env_var_name": args.env_var_name,
            "secret_value": args.value,
        }
        secret = application.upsert_secret(payload)
        _print_json(secret.to_public_dict())
        return 0

    if args.command == "delete-secret":
        application.delete_secret(args.secret_id)
        _print_json({"deleted": args.secret_id})
        return 0

    if args.command == "run":
        overrides = parse_key_value(args.set)
        if args.override_json.strip():
            overrides.update(json.loads(args.override_json))
        run = application.start_run(
            args.workspace,
            run_input_overrides=overrides,
            execute=not args.dry_run and not args.queue,
            enqueue=args.queue,
            requested_by="workspace_runner",
            max_attempts=args.max_attempts,
        )
        _print_json(public_run_summary(run))
        return 0

    if args.command == "cancel-run":
        run = application.cancel_run(args.run_id)
        _print_json(public_run_summary(run))
        return 0

    if args.command == "retry-run":
        run = application.retry_run(args.run_id)
        _print_json(public_run_summary(run))
        return 0

    if args.command == "resume-run":
        run = application.resume_run(args.run_id)
        _print_json(public_run_summary(run))
        return 0

    if args.command == "process-next":
        configure_worker_logging(level=args.log_level)
        worker_id = _runtime_worker_id(
            args.worker_id,
            default_prefix="cli_worker",
            process_id=os.getpid(),
        )
        worker = WorkerService(
            application=application,
            worker_id=worker_id,
            lease_seconds=args.lease_seconds,
            role=args.worker_role,
            logger=logging.getLogger("backend.worker.cli"),
        )
        run = worker.process_next(auto_retry_failed=not args.no_auto_retry)
        if run is None:
            print("No queued runs.")
            return 0
        _print_json(public_run_summary(run))
        return 0

    if args.command == "run-worker":
        configure_worker_logging(level=args.log_level)
        worker = WorkerService(
            application=application,
            worker_id=_runtime_worker_id(
                args.worker_id,
                default_prefix="cli_worker",
                process_id=os.getpid(),
            ),
            lease_seconds=args.lease_seconds,
            poll_interval_seconds=args.sleep_seconds,
            role=args.worker_role,
            logger=logging.getLogger("backend.worker.cli"),
        )
        processed = worker.run_loop(
            max_runs=max(0, int(args.max_runs)),
            auto_retry_failed=not args.no_auto_retry,
        )
        print(f"Worker processed {processed} run(s).")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
