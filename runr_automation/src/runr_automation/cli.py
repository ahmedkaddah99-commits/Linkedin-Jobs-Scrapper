"""Command-line shell for the local Runr automation controller."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from .config import load_config
from .linear_client import LinearGraphQLClient
from .lock import ControllerLock, LockUnavailable
from .migration import LinearMigrationClient, SubsystemMigrator
from .poller import Poller
from .reconciler import Reconciler
from .state import StateStore


COMMANDS = (
    "daemon",
    "once",
    "status",
    "doctor",
    "pause",
    "resume",
    "reconcile",
    "migrate-subsystems",
    "approve",
    "reject",
    "retry",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runr-auto")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparser = subparsers.add_parser(command)
        if command == "migrate-subsystems":
            modes = subparser.add_mutually_exclusive_group(required=True)
            modes.add_argument("--dry-run", action="store_true")
            modes.add_argument("--apply", action="store_true")
        elif command == "approve":
            subparser.add_argument("approval_id")
        elif command == "reject":
            subparser.add_argument("approval_id")
            subparser.add_argument("--reason", required=True)
        elif command == "retry":
            subparser.add_argument("job_id")
    return parser


def _doctor(config) -> int:
    StateStore(config.state_db)
    print(
        json.dumps(
            {
                "repo_root": str(config.repo_root),
                "data_dir": str(config.data_dir),
                "state_db": str(config.state_db),
                "python_executable": sys.executable,
                "providers": {
                    "order": config.provider_order,
                    "codex_available": shutil.which("codex") is not None,
                    "opencode_available": shutil.which("opencode") is not None,
                    "openrouter_enabled": config.openrouter_enabled,
                },
                "safe_stop": {
                    "max_attempt_seconds": config.max_attempt_seconds,
                    "max_attempt_tokens": config.max_attempt_tokens,
                    "reserve_tokens": config.reserve_tokens,
                },
            },
            sort_keys=True,
        )
    )
    return 0


def _status(config) -> int:
    store = StateStore(config.state_db)
    with store.connect() as connection:
        issues = connection.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print(
        json.dumps(
            {
                "issues": issues,
                "jobs": jobs,
                "paused": (config.data_dir / "paused").exists(),
                "state_db": str(config.state_db),
            }
        )
    )
    return 0


def _set_paused(config, paused: bool) -> int:
    marker = config.data_dir / "paused"
    config.data_dir.mkdir(parents=True, exist_ok=True)
    if paused:
        marker.write_text("paused by local operator\n", encoding="utf-8")
    else:
        marker.unlink(missing_ok=True)
    print(json.dumps({"paused": paused, "data_dir": str(config.data_dir)}))
    return 0


def _reconcile(config) -> int:
    result = Reconciler(StateStore(config.state_db)).run_once()
    print(json.dumps({"enqueued_jobs": result.enqueued_jobs}))
    return 0


def _once(config) -> int:
    token = os.environ.get("LINEAR_API_TOKEN")
    team_id = os.environ.get("RUNR_LINEAR_TEAM_ID")
    if not token or not team_id:
        print(
            "runr-auto once requires LINEAR_API_TOKEN and RUNR_LINEAR_TEAM_ID; no work was performed",
            file=sys.stderr,
        )
        return 2
    poll_result = Poller(
        StateStore(config.state_db),
        LinearGraphQLClient(token, team_id),
        overlap_seconds=config.poll_jitter_seconds,
    ).run_once()
    reconcile_result = Reconciler(StateStore(config.state_db)).run_once()
    print(
        json.dumps(
            {
                "pages": poll_result.pages,
                "recorded_events": poll_result.recorded_events,
                "enqueued_jobs": reconcile_result.enqueued_jobs,
                "watermark": poll_result.watermark,
            }
        )
    )
    return 0


def _migrate_subsystems(config, *, dry_run: bool) -> int:
    token = os.environ.get("LINEAR_API_TOKEN")
    team_id = os.environ.get("RUNR_LINEAR_TEAM_ID", "a6a93ab8-96eb-4ada-84e0-d4942d64db09")
    if not token:
        print("migrate-subsystems requires LINEAR_API_TOKEN; no Linear mutation was performed", file=sys.stderr)
        return 2
    result = SubsystemMigrator(
        LinearMigrationClient(token, team_id),
        snapshot_dir=config.data_dir / "backups",
        team_id=team_id,
    ).run(dry_run=dry_run)
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0 if result.success else 3


def _daemon(config, *, run_cycle=_once, sleep=time.sleep, max_cycles: int | None = None) -> int:
    lock = ControllerLock(config.data_dir / "locks" / "controller.lock")
    try:
        lock.acquire()
    except LockUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 4
    cycles = 0
    try:
        while max_cycles is None or cycles < max_cycles:
            if not (config.data_dir / "paused").exists():
                result = run_cycle(config)
                if result not in (0,):
                    return result
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                sleep(config.poll_interval_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        lock.release()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.repo_root, os.environ)
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "status":
        return _status(config)
    if args.command == "reconcile":
        return _reconcile(config)
    if args.command == "pause":
        return _set_paused(config, True)
    if args.command == "resume":
        return _set_paused(config, False)
    if args.command == "once":
        return _once(config)
    if args.command == "daemon":
        return _daemon(config)
    if args.command == "migrate-subsystems":
        return _migrate_subsystems(config, dry_run=args.dry_run)
    print(
        f"runr-auto {args.command} is not implemented in the core package phase",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
