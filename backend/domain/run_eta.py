from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


ACTIVE_RUN_STATUSES = {"planned", "queued", "running", "cancel_requested"}
MIN_SAMPLE_COUNT = 3


def _as_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _duration_seconds(started_at: Any, finished_at: Any) -> float | None:
    started = _as_datetime(started_at)
    finished = _as_datetime(finished_at)
    if started is None or finished is None or finished < started:
        return None
    return (finished - started).total_seconds()


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * ratio
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _workflow_stages(raw_stages: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "stage_id": str(stage.get("stage_id") or ""),
            "stage_type": str(stage.get("stage_type") or stage.get("stage_id") or ""),
        }
        for stage in raw_stages
        if str(stage.get("stage_id") or "").strip()
    ]


def build_run_eta(
    run,
    workflow_stages: Iterable[Mapping[str, Any]],
    historical_runs: Iterable[Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    calculated_at = now or datetime.now(timezone.utc)
    if str(getattr(run, "status", "") or "").strip().lower() not in ACTIVE_RUN_STATUSES:
        return {"state": "unavailable", "calculated_at": calculated_at.isoformat()}

    stages = _workflow_stages(workflow_stages)
    if not stages:
        return {"state": "estimating", "sample_count": 0, "calculated_at": calculated_at.isoformat()}

    stage_samples: dict[str, list[float]] = {}
    queue_samples: list[float] = []
    matching_runs = [
        item
        for item in historical_runs
        if str(getattr(item, "workflow_template_id", "") or "") == str(getattr(run, "workflow_template_id", "") or "")
        and str(getattr(item, "status", "") or "").lower() == "completed"
    ]
    for historical_run in matching_runs:
        queue_duration = _duration_seconds(
            getattr(historical_run, "queued_at", ""),
            getattr(historical_run, "started_at", ""),
        )
        if queue_duration is not None:
            queue_samples.append(queue_duration)
        for result in getattr(historical_run, "stage_results", []) or []:
            duration = _duration_seconds(result.started_at, result.finished_at)
            if duration is None:
                continue
            stage_type = str(result.stage_type or result.stage_id or "")
            stage_samples.setdefault(stage_type, []).append(duration)

    current_stage_id = str(getattr(run, "current_stage_id", "") or "")
    current_index = next(
        (index for index, stage in enumerate(stages) if stage["stage_id"] == current_stage_id),
        -1,
    )
    status = str(getattr(run, "status", "") or "").lower()
    queued_or_planned = status in {"planned", "queued"} or current_index < 0
    remaining_stages = stages if queued_or_planned else stages[current_index:]
    required_sample_sets: list[list[float]] = []
    if queued_or_planned:
        required_sample_sets.append(queue_samples)
    required_sample_sets.extend(stage_samples.get(stage["stage_type"], []) for stage in remaining_stages)
    sample_count = min((len(values) for values in required_sample_sets), default=0)
    if sample_count < MIN_SAMPLE_COUNT:
        return {
            "state": "estimating",
            "sample_count": sample_count,
            "calculated_at": calculated_at.isoformat(),
        }

    low_seconds = 0.0
    high_seconds = 0.0
    if queued_or_planned:
        queued_at = _as_datetime(getattr(run, "queued_at", "") or getattr(run, "created_at", ""))
        queue_elapsed = max((calculated_at - queued_at).total_seconds(), 0.0) if queued_at else 0.0
        low_seconds += max(_percentile(queue_samples, 0.2) - queue_elapsed, 0.0)
        high_seconds += max(_percentile(queue_samples, 0.8) - queue_elapsed, 0.0)

    progress = dict(getattr(run, "metadata", {}).get("progress") or {})
    current_started_at = _as_datetime(progress.get("started_at"))
    if current_started_at is None and not queued_or_planned:
        current_started_at = _as_datetime(getattr(run, "started_at", ""))
    current_elapsed = (
        max((calculated_at - current_started_at).total_seconds(), 0.0)
        if current_started_at is not None
        else 0.0
    )
    for index, stage in enumerate(remaining_stages):
        samples = stage_samples[stage["stage_type"]]
        stage_low = _percentile(samples, 0.2)
        stage_high = _percentile(samples, 0.8)
        if not queued_or_planned and index == 0:
            stage_low = max(stage_low - current_elapsed, 0.0)
            stage_high = max(stage_high - current_elapsed, 0.0)
        low_seconds += stage_low
        high_seconds += stage_high

    spread_ratio = high_seconds / max(low_seconds, 1.0)
    confidence = "high" if sample_count >= 10 and spread_ratio <= 1.6 else "medium" if sample_count >= 5 else "low"
    return {
        "state": "estimated",
        "remaining_seconds_low": int(round(low_seconds)),
        "remaining_seconds_high": max(int(round(high_seconds)), int(round(low_seconds))),
        "confidence": confidence,
        "sample_count": sample_count,
        "calculated_at": calculated_at.isoformat(),
    }


__all__ = ["build_run_eta"]
