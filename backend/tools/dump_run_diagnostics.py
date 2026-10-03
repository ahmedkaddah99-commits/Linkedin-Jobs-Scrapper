from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from backend.security.redaction import redact_sensitive_data


def _rows(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _tail(path: Path, *, lines: int) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-max(0, int(lines)) :]


def dump_run_diagnostics(
    *,
    db_path: Path,
    run_id: str,
    log_lines: int,
) -> dict[str, Any]:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        run_rows = _rows(
            connection,
            (
                "SELECT id, workspace_id, workflow_template_id, status, requested_by, user_id, "
                "created_at, updated_at, queued_at, started_at, finished_at, current_stage_id, "
                "last_error, attempt_count, max_attempts FROM runs WHERE id = ?"
            ),
            (run_id,),
        )
        if not run_rows:
            raise SystemExit(f"Run not found: {run_id}")
        stage_rows = _rows(
            connection,
            (
                "SELECT sequence_no, stage_id, stage_type, status, started_at, finished_at, "
                "error, metrics_json, output_keys_json, artifact_ids_json "
                "FROM run_stage_results WHERE run_id = ? ORDER BY sequence_no"
            ),
            (run_id,),
        )
        for row in stage_rows:
            row["metrics"] = _maybe_json(row.pop("metrics_json", "{}"))
            row["output_keys"] = _maybe_json(row.pop("output_keys_json", "[]"))
            row["artifact_ids"] = _maybe_json(row.pop("artifact_ids_json", "[]"))
        job_sets = _rows(
            connection,
            (
                "SELECT set_key, COUNT(*) AS job_count FROM run_jobs "
                "WHERE run_id = ? GROUP BY set_key ORDER BY set_key"
            ),
            (run_id,),
        )
        artifacts = _rows(
            connection,
            (
                "SELECT artifact_id, artifact_type, path, created_at FROM artifacts "
                "WHERE run_id = ? ORDER BY created_at, artifact_id"
            ),
            (run_id,),
        )
        workers = _rows(
            connection,
            (
                "SELECT worker_id, status, process_id, current_run_id, started_at, "
                "last_heartbeat_at, lease_expires_at FROM workers ORDER BY last_heartbeat_at DESC"
            ),
        )
    finally:
        connection.close()

    root = db_path.parent.parent if db_path.parent.name == ".backend_data" else Path.cwd()
    return redact_sensitive_data({
        "run": run_rows[0],
        "stages": stage_rows,
        "job_sets": job_sets,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "workers": workers,
        "log_files": {
            ".runr_dev_stdout.log": _tail(root / ".runr_dev_stdout.log", lines=log_lines),
            ".runr_dev_stderr.log": _tail(root / ".runr_dev_stderr.log", lines=log_lines),
            ".backend_worker_stderr.log": _tail(root / ".backend_worker_stderr.log", lines=log_lines),
            ".backend_api_stderr.log": _tail(root / ".backend_api_stderr.log", lines=log_lines),
        },
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump local diagnostics for a Runr workspace run.")
    parser.add_argument("run_id", help="Run id, for example run_78413d594cdd4270.")
    parser.add_argument(
        "--db",
        default=str(Path(".backend_data") / "backend.sqlite3"),
        help="Path to backend SQLite database.",
    )
    parser.add_argument("--log-lines", type=int, default=80, help="Number of lines to include from each local log.")
    args = parser.parse_args()

    payload = dump_run_diagnostics(
        db_path=Path(args.db),
        run_id=str(args.run_id),
        log_lines=max(0, int(args.log_lines)),
    )
    sys.stdout.buffer.write(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
