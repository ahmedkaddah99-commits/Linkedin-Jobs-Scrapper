"""Write a small durable receipt for an independent source or publisher run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_metrics(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, ""
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = {}
    return (dict(value) if isinstance(value, dict) else {}), hashlib.sha256(raw).hexdigest()


def _duration_seconds(started_at: str, finished_at: str) -> float | None:
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if finish.tzinfo is None:
        finish = finish.replace(tzinfo=timezone.utc)
    return max(0.0, (finish - start).total_seconds())


def _read_cgroup_resources() -> dict[str, Any]:
    """Capture cheap cgroup counters when running under systemd on Linux."""

    root = Path(os.environ.get("RUNR_RECEIPT_CGROUP_PATH", "/sys/fs/cgroup"))
    result: dict[str, Any] = {}
    memory_peak = root / "memory.peak"
    cpu_stat = root / "cpu.stat"
    try:
        if memory_peak.is_file():
            result["memory_peak_bytes"] = int(memory_peak.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    try:
        if cpu_stat.is_file():
            for line in cpu_stat.read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition(" ")
                if key in {"usage_usec", "user_usec", "system_usec"} and value.strip().isdigit():
                    result[f"cpu_{key}"] = int(value.strip())
    except OSError:
        pass
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--finished-at", default="")
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-commit", default="")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    metrics, metrics_sha256 = _read_metrics(args.metrics)
    finished_at = args.finished_at or _now()
    receipt = {
        "schema_version": "runr.acquisition.receipt.v1",
        "source": args.source,
        "status": args.status,
        "exit_code": int(args.exit_code),
        "started_at": args.started_at,
        "finished_at": finished_at,
        "duration_seconds": _duration_seconds(args.started_at, finished_at),
        "release_commit": args.release_commit,
        "metrics_path": str(args.metrics),
        "metrics_sha256": metrics_sha256,
        "resource": _read_cgroup_resources(),
        "last_success_at": finished_at if args.status == "succeeded" and int(args.exit_code) == 0 else "",
        "metrics": metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    print(json.dumps(run(build_parser().parse_args()), ensure_ascii=False, indent=2))
