"""Command-line shell for the local Runr automation controller."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import load_config
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
                "provider_check": "not implemented in core package phase",
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
    print(json.dumps({"issues": issues, "jobs": jobs, "state_db": str(config.state_db)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.repo_root, os.environ)
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "status":
        return _status(config)
    print(
        f"runr-auto {args.command} is not implemented in the core package phase",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
