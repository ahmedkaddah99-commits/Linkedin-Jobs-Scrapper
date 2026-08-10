"""Plan or safely re-run the connector-independent acquisition rules.

The default command is read-only.  Apply mode requires --yes and, for a
remote Turso target, --allow-remote-additive-rollback.  The reprocessor never
updates immutable source observations, merges duplicate jobs, or promotes a
publication automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.acquisition.reprocessing import build_reprocessing_plan, run_reprocessing


def _assert_project_interpreter() -> None:
    expected = Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "python.exe"
    actual = Path(sys.executable).resolve()
    if actual != expected:
        raise RuntimeError(
            "reprocessing must run with the project interpreter "
            f"{expected}; refusing {actual}"
        )
    if sys.version_info[:3] != (3, 12, 7):
        raise RuntimeError(f"reprocessing requires Python 3.12.7; found {sys.version.split()[0]}")


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def main() -> int:
    _assert_project_interpreter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path("user_config/.env"))
    parser.add_argument("--database-root", type=Path, default=Path(".backend_data"))
    parser.add_argument("--scope-json", default="{}", help="JSON object limiting the run; recorded for audit")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int, default=100, help="Maximum committed batches per invocation")
    parser.add_argument("--stale-after-seconds", type=int, default=30 * 60, help="Lease age required before reclaiming a running invocation")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Confirm additive reprocessing")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--resume", dest="resume_id", default="")
    parser.add_argument("--allow-remote-additive-rollback", action="store_true")
    args = parser.parse_args()
    _load_env(args.env_file)
    try:
        scope = json.loads(args.scope_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--scope-json must be a JSON object: {exc}")
    if not isinstance(scope, dict):
        parser.error("--scope-json must be a JSON object")
    if args.apply and not args.yes:
        parser.error("--apply requires --yes")
    if args.apply:
        result = run_reprocessing(
            args.database_root,
            apply=True,
            batch_size=max(1, args.batch_size),
            max_batches=max(1, args.max_batches),
            stale_after_seconds=max(1, args.stale_after_seconds),
            idempotency_key=args.idempotency_key,
            resume_id=args.resume_id,
            scope=scope,
            allow_remote_additive_rollback=args.allow_remote_additive_rollback,
        )
    else:
        result = {"status": "planned", "plan": build_reprocessing_plan(args.database_root, scope=scope)}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") not in {"blocked", "failed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
