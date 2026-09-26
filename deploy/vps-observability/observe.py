"""Bounded VPS acquisition health snapshots; no application secrets or row payloads.

Default mode is read-only. Installed service uses --enforce-policy to restore the
owner-approved dedicated timers unless a documented, time-limited pause exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCES = ("linkedin", "employer", "publisher")
COUNTS = {
    "jobs_written", "jobs_published", "jobs_rejected", "exported_jobs", "persisted_jobs",
    "companies_input", "companies_completed", "companies_failed", "companies_processed",
    "selected_companies", "requests_used", "requests_made", "request_count",
    "detail_successes", "detail_failures", "observations_written", "published_jobs",
    "accepted_jobs", "rejected_jobs", "delivered_jobs", "remaining_jobs",
    "requests", "total_attempts", "browser_navigations", "fallback_attempts",
    "companies_deferred_budget", "companies_skipped_resume",
    "jobs_observed", "jobs_new", "jobs_updated", "jobs_unchanged", "jobs_closed", "jobs_duplicates",
}
PROPERTIES = (
    "LoadState", "ActiveState", "SubState", "UnitFileState", "Result", "ExecMainStatus",
    "ExecMainStartTimestamp", "ExecMainExitTimestamp", "NextElapseUSecRealtime",
    "CPUUsageNSec", "MemoryPeak", "MemoryCurrent", "TasksCurrent",
)


def epoch(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def service_start_epoch(service):
    try:
        return datetime.strptime(service.get("ExecMainStartTimestamp", ""), "%a %Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    return result.returncode, result.stdout


def unit_state(unit):
    code, output = command("systemctl", "show", unit, "--no-pager", *["--property=" + p for p in PROPERTIES])
    state = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    state["query_ok"] = code == 0 and state.get("LoadState") == "loaded"
    return state


def json_objects(path):
    """Collectors write pretty JSON mixed with log lines; preserve final summaries."""
    if not path.is_file():
        return []
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 2_000_000))
        text = stream.read().decode("utf-8", errors="replace")
    decoder, values, offset = json.JSONDecoder(), [], 0
    while (start := text.find("{", offset)) >= 0:
        try:
            obj, length = decoder.raw_decode(text[start:])
            values.append(obj)
            offset = start + length
        except ValueError:
            offset = start + 1
    return values


def summarize(objects):
    counts, outcome = {}, "unknown"
    def visit(obj):
        nonlocal outcome
        if not isinstance(obj, dict):
            return
        for key, value in obj.items():
            if key in COUNTS and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                counts[key] = value
            elif key in {"run_status", "run_outcome"} and isinstance(value, str):
                normalized = value.casefold()
                if normalized in {"success", "succeeded", "completed", "partial", "failed", "blocked", "error"}:
                    outcome = normalized
            elif key == "company_statuses" and isinstance(value, dict):
                partial = sum(v for k, v in value.items() if k in {"partial", "source_failed", "discovery_failed"} and isinstance(v, int))
                counts["companies_partial_or_failed"] = partial
                if partial:
                    outcome = "partial"
            elif isinstance(value, dict):
                visit(value)
    for obj in objects:
        visit(obj)
        if isinstance(obj, dict):
            status = obj.get("status")
            if status in {"published", "completed", "succeeded", "no_changes"} and outcome == "unknown":
                outcome = "completed"
            elif status == "degraded":
                outcome = "partial"
            elif status in {"failed", "error", "recovery_required"}:
                outcome = "failed"
            elif status == "already_running":
                outcome = "blocked"
    return counts, outcome


def pause_state(path, now):
    if not path.exists():
        return False, ""
    try:
        pause = json.loads(path.read_text())
        expiry = epoch(pause.get("expires_at"))
        if pause.get("approved_by") == "Ahmed Kaddah" and pause.get("reason") and expiry and now < expiry:
            return True, str(pause["reason"])[:200]
    except (OSError, ValueError, TypeError):
        pass
    return False, "invalid_or_expired_pause"


def snapshot(receipts, *, enforce=False, pause_path=Path("/etc/runr/acquisition-pause.json"), now=None):
    now = now or datetime.now(timezone.utc).timestamp()
    paused, pause_reason = pause_state(pause_path, now)
    sources, repairs = {}, []
    for source in SOURCES:
        timer_name = f"runr-acquisition-{source}.timer"
        timer, service = unit_state(timer_name), unit_state(f"runr-acquisition-{source}.service")
        if enforce and not paused and (timer.get("ActiveState") != "active" or timer.get("UnitFileState") != "enabled"):
            code, _ = command("systemctl", "enable", "--now", timer_name)
            repairs.append({"unit": timer_name, "action": "restore_owner_approved_timer", "succeeded": code == 0})
            timer = unit_state(timer_name)
        receipt_path = receipts / f"{source}-latest.json"
        try:
            receipt = json.loads(receipt_path.read_text())
            if not isinstance(receipt, dict):
                receipt = {}
        except (OSError, ValueError):
            receipt = {}
        metrics_path = receipts / f"{source}-latest-metrics.json"
        # A running wrapper replaces this file before it replaces its receipt.
        # Never attribute an in-flight metrics file to the previous completed run.
        metrics_match = False
        if metrics_path.is_file() and receipt.get("metrics_sha256"):
            with metrics_path.open("rb") as stream:
                metrics_match = hashlib.file_digest(stream, "sha256").hexdigest() == receipt["metrics_sha256"]
        objects = json_objects(metrics_path) if metrics_match else []
        counts, outcome = summarize([receipt.get("metrics", {}), *objects])
        finished = epoch(receipt.get("finished_at"))
        last_run_age = max(0, now - finished) if finished is not None else None
        wrapper_ok = receipt.get("status") == "succeeded" and receipt.get("exit_code") == 0
        running = service.get("ActiveState") in {"active", "activating"}
        started = service_start_epoch(service)
        progress = {}
        if source == "publisher" and started:
            try:
                candidate = json.loads((receipts / "publisher-progress.json").read_text())
                progress_at = epoch(candidate.get("timestamp"))
                if progress_at and progress_at >= started and candidate.get("phase") in {
                    "initializing_database", "identity_reconciliation", "source_loading",
                    "targets_registration", "cycle_claim", "task_registration", "delivery",
                    "publication", "checkpoints", "completed", "failed",
                }:
                    progress = {"phase": candidate["phase"], "timestamp": candidate["timestamp"],
                                "age_seconds": max(0, now - progress_at),
                                "counts": {k: v for k, v in candidate.get("counts", {}).items()
                                           if k in {"identities", "companies", "targets", "companies_completed"}
                                           and isinstance(v, int) and not isinstance(v, bool)}}
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        reasons = []
        if not timer.get("query_ok") or not service.get("query_ok"):
            reasons.append("unit_unavailable")
        if timer.get("UnitFileState") != "enabled" or timer.get("ActiveState") != "active":
            reasons.append("timer_disabled")
        if not receipt:
            reasons.append("receipt_missing")
        elif last_run_age is None or last_run_age > 30 * 3600:
            reasons.append("receipt_stale")
        if receipt and not wrapper_ok:
            reasons.append("last_run_failed")
        if outcome in {"failed", "error", "blocked", "partial"}:
            reasons.append("collector_" + outcome)
        if receipt and outcome == "unknown":
            reasons.append("collector_outcome_unverified")
        if service.get("ActiveState") == "failed":
            reasons.append("service_failed")
        sources[source] = {
            "timer": timer, "service": service, "running": running,
            "running_elapsed_seconds": max(0, now - started) if running and started else 0,
            "progress": progress,
            "receipt_present": bool(receipt), "last_run_finished_at": receipt.get("finished_at", ""),
            "last_run_age_seconds": last_run_age, "duration_seconds": receipt.get("duration_seconds"),
            "wrapper_status": receipt.get("status", "unknown"), "exit_code": receipt.get("exit_code"),
            "release_commit": str(receipt.get("release_commit", ""))[:64],
            "collector_outcome": outcome, "counts": counts,
            "counts_scope": "collector_reported_totals_not_necessarily_new_jobs",
            "health": "paused" if paused else ("running" if running else ("degraded" if reasons else "healthy")),
            "reasons": reasons,
        }
    return {
        "schema": "runr.vps.health.v1", "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "host": socket.gethostname(), "paused": paused, "pause_reason": pause_reason,
        "legacy_scheduler": "disabled_intentionally_dedicated_timers_own_collection",
        "sources": sources, "repairs": repairs,
    }


def prometheus(data):
    lines = [f'runr_observer_timestamp_seconds {epoch(data["timestamp"])}', f'runr_acquisition_owner_paused {int(data["paused"])}']
    if "catalog" in data:
        catalog = data["catalog"]
        lines.append(f'runr_catalog_access_ok {int(catalog.get("access_ok", False))}')
        if "head_jobs" in catalog:
            lines.append(f'runr_catalog_head_jobs {catalog["head_jobs"]}')
        checked = epoch(catalog.get("checked_at"))
        if checked is not None:
            lines.append(f'runr_catalog_checked_timestamp_seconds {checked}')
        head_at = epoch(catalog.get("head", {}).get("updated_at"))
        if head_at is not None:
            lines.append(f'runr_catalog_head_timestamp_seconds {head_at}')
    for source, state in data["sources"].items():
        labels = '{source="' + source + '"}'
        values = {
            "timer_enabled": int(state["timer"].get("UnitFileState") == "enabled"),
            "timer_active": int(state["timer"].get("ActiveState") == "active"),
            "running": int(state["running"]), "receipt_present": int(state["receipt_present"]),
            "running_elapsed_seconds": state.get("running_elapsed_seconds", 0),
            "last_run_failed": int("last_run_failed" in state["reasons"] or "service_failed" in state["reasons"]),
            "last_run_partial": int(state["collector_outcome"] == "partial"),
            "last_run_outcome_known": int(state["collector_outcome"] != "unknown"),
            "health_degraded": int(bool(state["reasons"])),
            "last_run_timestamp_seconds": epoch(state["last_run_finished_at"]),
            "last_run_age_seconds": state["last_run_age_seconds"], "last_run_duration_seconds": state["duration_seconds"],
        }
        values.update({"last_run_" + k: v for k, v in state["counts"].items()})
        for prop, metric, divisor in (("MemoryPeak", "service_memory_peak_bytes", 1), ("MemoryCurrent", "service_memory_current_bytes", 1), ("CPUUsageNSec", "service_cpu_seconds", 1e9), ("TasksCurrent", "service_tasks", 1)):
            raw = state["service"].get(prop, "")
            if raw.isdigit():
                values[metric] = int(raw) / divisor
        for name, value in values.items():
            if isinstance(value, (int, float)) and math.isfinite(value):
                lines.append(f"runr_acquisition_{name}{labels} {value}")
        progress = state.get("progress", {})
        if progress:
            phase_labels = '{source="' + source + '",phase="' + progress['phase'] + '"}'
            lines.append(f'runr_acquisition_progress_timestamp_seconds{phase_labels} {epoch(progress["timestamp"])}')
            for name, value in progress['counts'].items():
                lines.append(f'runr_acquisition_progress_{name}{labels} {value}')
    return "\n".join(lines) + "\n"


def atomic_write(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, 0o644)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, default=Path("/srv/runr/exports/receipts"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--enforce-policy", action="store_true")
    parser.add_argument("--catalog-env", type=Path)
    args = parser.parse_args()
    data = snapshot(args.receipts, enforce=args.enforce_policy)
    if args.catalog_env:
        from catalog import check_catalog
        cache = args.output_dir / "catalog.json" if args.output_dir else None
        try:
            cached = json.loads(cache.read_text()) if cache else {}
        except (OSError, ValueError):
            cached = {}
        checked = epoch(cached.get("checked_at"))
        data["catalog"] = cached if checked and epoch(data["timestamp"]) - checked < 300 else check_catalog(args.catalog_env)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(args.output_dir / "health.json", json.dumps(data, indent=2) + "\n")
        atomic_write(args.output_dir / "acquisition.prom", prometheus(data))
        if "catalog" in data:
            atomic_write(args.output_dir / "catalog.json", json.dumps(data["catalog"], indent=2) + "\n")
        events = args.output_dir / "health-events.jsonl"
        # Keep bounded local history (~one week); journal retains rotation evidence.
        if events.exists() and events.stat().st_size > 20_000_000:
            events.replace(events.with_suffix(".jsonl.1"))
        with events.open("a", encoding="utf-8") as stream:
            for source, state in data["sources"].items():
                stream.write(json.dumps({"event": "runr_acquisition_health", "timestamp": data["timestamp"], "source": source, **state}) + "\n")
        os.chmod(events, 0o644)
    print(json.dumps(data))


if __name__ == "__main__":
    main()
