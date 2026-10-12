"""Bounded, resumable frozen-source catch-up. Linux production entry point.

The operation lock protects its immutable inputs. The normal publisher lock
serializes the frozen delivery window; collectors are locked only during capture.
No checkpoint resets, quality bypasses, or provider requests are performed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.snapshot_producer_states import snapshot_database


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def lock(path, deadline):
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Lock deadline: {path.name}")
                time.sleep(1)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def checkpoints(database):
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(
            "SELECT source,source_rowid,source_watermark,bootstrap_complete "
            "FROM acquisition_publisher_checkpoints WHERE source IN ('linkedin','employer_site')"
        )]


def delivery_complete(rows, boundary):
    return {r["source"] for r in rows} == {"linkedin", "employer_site"} and all(
        r["bootstrap_complete"] and r["source_watermark"] >= boundary for r in rows
    )


def capture(args, deadline):
    operation = args.operation
    receipt = operation / "snapshot.json"
    if receipt.exists():
        state = json.loads(receipt.read_text(encoding="utf-8"))
        for name, expected in state["hashes"].items():
            if digest(operation / name) != expected:
                raise ValueError(f"Frozen input changed: {name}")
        if state["catalog"] != str(args.catalog):
            raise ValueError("Cannot resume against a different catalog")
        return state
    # Failed captures remain for diagnosis. Never silently overwrite evidence.
    if (operation / "linkedin.db").exists() or (operation / "employer.db").exists():
        raise ValueError("Incomplete capture: inspect it and choose a new operation directory")
    with ExitStack() as stack:
        for name in ("linkedin", "employer"):
            stack.enter_context(lock(args.locks / (name + ".lock"), deadline))
        boundary = utc_now()
        metrics = {}
        for name, source in (("linkedin", args.linkedin_state), ("employer", args.employer_state)):
            metrics[name] = snapshot_database(source, operation / (name + ".db"))
    # Freeze manifest bundle (including its raw sidecar) and reviewed mapping.
    bundle = operation / "inputs"
    shutil.copytree(args.manifest.resolve().parent, bundle)
    manifest = bundle / args.manifest.name
    crosswalk = None
    if args.crosswalk:
        crosswalk = operation / "crosswalk.json"
        shutil.copy2(args.crosswalk, crosswalk)
    paths = [operation / "linkedin.db", operation / "employer.db", *bundle.rglob("*")]
    if crosswalk:
        paths.append(crosswalk)
    state = {"schema": "runr.catchup.v1", "captured_at": boundary,
             "catalog": str(args.catalog), "manifest": str(manifest),
             "initial_checkpoints": checkpoints(args.catalog),
             "crosswalk": str(crosswalk) if crosswalk else None,
             "capture": metrics, "hashes": {
                 str(p.relative_to(operation)): digest(p) for p in paths if p.is_file()
             }}
    write_json(receipt, state)
    return state


def run(args):
    args.operation.mkdir(parents=True, exist_ok=True)
    from backend.database.connection import database_target_key
    if database_target_key(args.data_dir / "backend.sqlite3") != "sqlite:" + str(args.catalog):
        raise ValueError("Delivery database binding differs from the audited catalog")
    checkpoints(args.catalog)  # Verify permissions before taking expensive snapshots.
    write_json(args.operation / "status.json", {"status": "waiting_for_capture_locks", "checked_at": utc_now()})
    deadline = time.monotonic() + args.max_seconds
    with lock(args.operation / "operation.lock", deadline), lock(args.locks / "publisher.lock", deadline):
        state = capture(args, deadline)
        expected_path = args.operation / "expected-checkpoints.json"
        expected = (json.loads(expected_path.read_text(encoding="utf-8"))
                    if expected_path.exists() else state["initial_checkpoints"])
        if checkpoints(args.catalog) != expected:
            raise ValueError("Catalog checkpoints changed outside this operation; inspect before resuming")
        status_path = args.operation / "status.json"
        rounds = 0
        while time.monotonic() < deadline:
            with ExitStack():
                rows = checkpoints(args.catalog)
                if delivery_complete(rows, state["captured_at"]):
                    write_json(status_path, {"status": "source_delivery_complete",
                        "customer_readiness": "requires_outcome_audit", "checked_at": utc_now(),
                        "captured_at": state["captured_at"], "checkpoints": rows})
                    return 0
                if any(r["source_watermark"] > state["captured_at"] for r in rows):
                    raise ValueError("Another publisher advanced beyond the snapshot; create a new operation")
                write_json(status_path, {"status": "delivering", "checked_at": utc_now(),
                    "captured_at": state["captured_at"], "checkpoints": rows, "rounds_this_run": rounds})
                command = [sys.executable, str(ROOT / "scripts/publish_producer_states.py"),
                    "--manifest", state["manifest"], "--linkedin-state", str(args.operation / "linkedin.db"),
                    "--employer-state", str(args.operation / "employer.db"),
                    "--data-dir", str(args.data_dir), "--source-version", args.source_version,
                    "--snapshot-captured-at", state["captured_at"], "--max-companies", "20000"]
                if state["crosswalk"]:
                    command.extend(["--identity-crosswalk", state["crosswalk"]])
                with (args.operation / "round-latest.log").open("w", encoding="utf-8") as log:
                    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT,
                        timeout=max(1, deadline - time.monotonic()),
                        env={**os.environ, "RUNR_PUBLISHER_SOURCE_ROW_BATCH_SIZE": str(args.batch_size)})
                after = checkpoints(args.catalog)
                write_json(expected_path, after)
                with (args.operation / "rounds.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"at": utc_now(), "before": rows, "after": after}) + "\n")
                if after == rows:
                    raise RuntimeError("Delivery made no checkpoint progress; inspect round-latest.log")
                rounds += 1
        write_json(status_path, {"status": "time_limit", "checked_at": utc_now(),
            "checkpoints": checkpoints(args.catalog), "resumable": True})
        return 124


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("operation", "catalog", "data-dir", "manifest", "linkedin-state", "employer-state", "locks"):
        parser.add_argument("--" + name, type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument("--crosswalk", type=lambda p: Path(p).resolve())
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--max-seconds", type=int, default=3600)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if args.max_seconds <= 0 or args.batch_size <= 0:
        parser.error("limits must be positive")
    try:
        return run(args)
    except Exception as exc:
        args.operation.mkdir(parents=True, exist_ok=True)
        write_json(args.operation / "status.json", {"status": "failed", "checked_at": utc_now(),
            "error_type": type(exc).__name__, "error": str(exc)[:500]})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
