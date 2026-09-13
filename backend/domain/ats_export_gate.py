from __future__ import annotations

from typing import Any, Mapping

from .phase0_contracts import normalize_ats_export_gate


def _gate_metadata(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    metadata = payload.get("metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _is_stalled(payload: Mapping[str, Any] | None, gate: Mapping[str, Any]) -> bool:
    metadata = _gate_metadata(payload)
    stop_reason = str(metadata.get("stop_reason") or "").strip().lower()
    if stop_reason == "score_stalled":
        return True
    return str(gate.get("gate_state") or "").strip().lower() in {"blocked", "warning_acknowledged"}


def _blocked_warning(gate: Mapping[str, Any]) -> str:
    return (
        f"We could not reach {gate['target_score']}%. "
        f"Best score reached: {gate['best_score']}%. "
        "Review the missing requirements or continue anyway."
    )


def evaluate_ats_export_gate(payload: Mapping[str, Any] | None, *, export_anyway: bool = False) -> dict[str, Any]:
    gate = normalize_ats_export_gate(payload)
    stalled = _is_stalled(payload, gate)

    if export_anyway:
        if gate["best_score"] >= gate["target_score"] or gate["attempt_count"] >= gate["max_attempts"] or stalled:
            gate["gate_state"] = "exported_anyway"
            gate["can_export_final"] = True
            gate["export_anyway_allowed"] = True
            if not gate["last_warning"] and gate["best_score"] < gate["target_score"]:
                gate["last_warning"] = _blocked_warning(gate)
            return gate
        gate["export_anyway_allowed"] = False

    if gate["best_score"] >= gate["target_score"]:
        gate["gate_state"] = "passed"
        gate["can_export_final"] = True
        gate["export_anyway_allowed"] = False
        gate["last_warning"] = ""
    elif gate["attempt_count"] >= gate["max_attempts"] or stalled:
        gate["gate_state"] = "blocked"
        gate["can_export_final"] = False
        gate["export_anyway_allowed"] = True
        if not gate["last_warning"]:
            gate["last_warning"] = _blocked_warning(gate)
    else:
        gate["gate_state"] = "scoring"
        gate["can_export_final"] = False
        gate["export_anyway_allowed"] = False
        if not gate["last_warning"]:
            gate["last_warning"] = "Final CV export is blocked until the ATS score target is reached."
    return gate


__all__ = ["evaluate_ats_export_gate"]
