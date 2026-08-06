"""Production rollout gates for the shared Jobs catalog.

The rollout is deliberately server-controlled.  A browser cannot advance a
stage, enable a source, publish a catalog, or turn on the scheduler.  The
service records measured evidence in the existing config store and exposes an
admin-only status/report surface for the operational rollout.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from backend.acquisition.manifest import load_phase_a_manifest
from backend.config.plans import PLAN_ORDER, get_plan


PHASE_I_STAGES = (
    "preflight",
    "one_source_production",
    "staging_publication",
    "internal_cohort",
    "selected_cohort",
    "source_expansion",
    "daily_scheduler",
    "pro_checkout",
    "complete",
)

PHASE_I_DEFAULT_CONFIG: dict[str, Any] = {
    "rollout_enabled": False,
    "stage": "preflight",
    "production_source_id": "",
    "additional_source_ids": [],
    "internal_cohort_user_ids": [],
    "selected_cohort_user_ids": [],
    "user_cohort_gate_enabled": False,
    "production_publication_enabled": False,
    "stale_catalog_alert_hours": 48,
    "failed_cycle_alert_threshold": 1,
    "failed_cycle_alert_window_hours": 48,
    "global_request_ceiling": 100,
    "cycle_request_ceiling": 16,
    "cycle_credit_ceiling": 0,
    "target_request_ceilings": {},
    "target_credit_ceilings": {},
    "earlier_phases_accepted": False,
    "apply_quality_verified": False,
    "catalog_inspection_approved": False,
    "checkout_gate_enabled": False,
    "rollout_history": [],
}

_EVIDENCE_KEYS = {
    "earlier_phases_accepted",
    "apply_quality_verified",
    "catalog_inspection_approved",
}


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on", "enabled"}


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(_text(item) for item in value if _text(item)))


def _age_hours(value: Any) -> float | None:
    if not _text(value):
        return None
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600)
    except ValueError:
        return None


def _config(config_store: Any, key: str, default: Any = None) -> Any:
    getter = getattr(config_store, "get_value", None)
    return getter(key, default) if callable(getter) else default


def _set_config(config_store: Any, key: str, value: Any) -> None:
    setter = getattr(config_store, "set_value", None)
    if not callable(setter):
        raise ValueError("Production rollout requires a durable config store.")
    setter(key, value)


def _history(config_store: Any) -> list[dict[str, Any]]:
    value = _config(config_store, "acquisition.phase_i.rollout_history", [])
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def phase_i_config(config_store: Any, name: str, default: Any = None) -> Any:
    fallback = PHASE_I_DEFAULT_CONFIG.get(name, default)
    return _config(config_store, f"acquisition.phase_i.{name}", fallback)


def catalog_user_access(config_store: Any, user_id: str) -> bool:
    """Return whether a user is in the explicitly enabled production cohort."""

    if not _bool(phase_i_config(config_store, "user_cohort_gate_enabled", False)):
        return True
    stage = _text(phase_i_config(config_store, "stage", "preflight"))
    allowed = set(_list(phase_i_config(config_store, "internal_cohort_user_ids", [])))
    if stage in {"selected_cohort", "source_expansion", "daily_scheduler", "pro_checkout", "complete"}:
        allowed.update(_list(phase_i_config(config_store, "selected_cohort_user_ids", [])))
    return _text(user_id) in allowed


def build_rollout_health(
    config_store: Any,
    acquisition_store: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build operational health and alert data from durable acquisition facts."""

    current = now or datetime.now(timezone.utc)
    stale_limit = _int(phase_i_config(config_store, "stale_catalog_alert_hours", 48), 48)
    failed_limit = max(1, _int(phase_i_config(config_store, "failed_cycle_alert_threshold", 1), 1))
    failed_window = _int(phase_i_config(config_store, "failed_cycle_alert_window_hours", 48), 48)
    alerts: list[dict[str, Any]] = []
    public = acquisition_store.get_public_catalog(limit=1, offset=0) if acquisition_store is not None else {}
    publication = dict(public.get("publication") or {})
    publication_age = _age_hours(publication.get("published_at"))
    if publication_age is None or publication_age > stale_limit:
        alerts.append(
            {
                "type": "stale_catalog",
                "severity": "critical" if publication_age is None else "warning",
                "age_hours": round(publication_age, 2) if publication_age is not None else None,
                "threshold_hours": stale_limit,
            }
        )

    cycles = acquisition_store.list_cycles(limit=100, offset=0) if acquisition_store is not None else []
    failed_cycles = []
    for cycle in cycles:
        age = _age_hours(cycle.get("completed_at") or cycle.get("scheduled_at"))
        if age is not None and age <= failed_window and _text(cycle.get("status")) in {
            "failed",
            "recovery_required",
            "blocked",
        }:
            failed_cycles.append(cycle)
    if len(failed_cycles) >= failed_limit:
        alerts.append(
            {
                "type": "failed_cycles",
                "severity": "critical",
                "count": len(failed_cycles),
                "threshold": failed_limit,
                "window_hours": failed_window,
            }
        )

    return {
        "state": "healthy" if not alerts else "alerting",
        "checked_at": current.isoformat(),
        "publication": {
            "publication_id": _text(publication.get("publication_id")) or None,
            "cycle_id": _text(publication.get("cycle_id")) or None,
            "published_at": _text(publication.get("published_at")) or None,
            "freshness": _text(public.get("freshness")) or "unavailable",
            "age_hours": round(publication_age, 2) if publication_age is not None else None,
        },
        "failed_cycles": [
            {"cycle_id": _text(item.get("cycle_id")), "status": _text(item.get("status"))}
            for item in failed_cycles
        ],
        "alerts": alerts,
    }


class ProductionRolloutService:
    def __init__(self, repositories: Any, event_emitter: Callable[..., None] | None = None):
        self.repositories = repositories
        self.event_emitter = event_emitter

    @property
    def config_store(self) -> Any:
        return getattr(self.repositories, "config_store", None)

    @property
    def acquisition_store(self) -> Any:
        return getattr(self.repositories, "acquisition_store", None)

    def _emit(self, event_name: str, **payload: Any) -> None:
        if callable(self.event_emitter):
            self.event_emitter(event_name, source="production_rollout", payload=payload)

    def _source_context(self) -> dict[str, Any]:
        source_id = _text(phase_i_config(self.config_store, "production_source_id", ""))
        if not source_id or self.acquisition_store is None:
            return {"source_id": source_id, "target": None, "history": None, "metrics": None}
        try:
            target = self.acquisition_store.get_target(source_id)
            history = self.acquisition_store.get_target_history(source_id)
        except KeyError:
            return {"source_id": source_id, "target": None, "history": None, "metrics": None}
        metrics = None
        for cycle in self.acquisition_store.list_cycles(limit=50, offset=0):
            cycle_id = _text(cycle.get("cycle_id"))
            if not cycle_id:
                continue
            for item in self.acquisition_store.get_cycle_source_metrics(cycle_id):
                if _text(item.get("target_id")) == source_id:
                    metrics = item
                    break
            if metrics is not None:
                break
        return {"source_id": source_id, "target": target, "history": history, "metrics": metrics}

    def _gates(self) -> dict[str, dict[str, Any]]:
        source = self._source_context()
        target = source.get("target") or {}
        history = source.get("history") or {}
        metrics = source.get("metrics") or {}
        attempts = history.get("attempts") or []
        requests = history.get("requests") or []
        measured = bool(requests) and bool(attempts)
        productive = _text(target.get("maturity_state")) == "productive"
        cost_value = metrics.get("cost_per_new_published_job") if metrics else None
        cost_known = (
            bool(metrics)
            and int(metrics.get("jobs_published") or metrics.get("jobs_new") or 0) > 0
            and cost_value not in (None, "")
        )
        freshness_age = _age_hours(target.get("last_success_at"))
        freshness_ok = freshness_age is not None and freshness_age <= _int(
            phase_i_config(self.config_store, "stale_catalog_alert_hours", 48), 48
        )
        staging = self.acquisition_store.get_staging_catalog(limit=1, offset=0) if self.acquisition_store else {}
        staging_ready = bool(staging.get("publication"))
        cohorts_ready = bool(_list(phase_i_config(self.config_store, "internal_cohort_user_ids", [])))
        selected_ready = bool(_list(phase_i_config(self.config_store, "selected_cohort_user_ids", [])))
        evidence = {
            name: _bool(phase_i_config(self.config_store, name, False)) for name in _EVIDENCE_KEYS
        }
        return {
            "earlier_phases_accepted": {"passed": evidence["earlier_phases_accepted"]},
            "source_configured": {"passed": bool(source.get("source_id")), "source_id": source.get("source_id")},
            "source_measured": {"passed": measured, "request_count": len(requests), "attempt_count": len(attempts)},
            "source_productive": {"passed": productive, "maturity_state": _text(target.get("maturity_state")) or "unknown"},
            "cost_measured": {
                "passed": cost_known,
                "cost_per_new_published_job": metrics.get("cost_per_new_published_job") if metrics else None,
            },
            "apply_quality_verified": {"passed": evidence["apply_quality_verified"]},
            "source_fresh": {"passed": freshness_ok, "age_hours": freshness_age},
            "staging_ready": {"passed": staging_ready},
            "catalog_inspection_approved": {"passed": evidence["catalog_inspection_approved"]},
            "internal_cohort_configured": {"passed": cohorts_ready},
            "selected_cohort_configured": {"passed": selected_ready},
            "cohort_gate_enabled": {
                "passed": _bool(phase_i_config(self.config_store, "user_cohort_gate_enabled", False)),
            },
            "creem_products_configured": {
                "passed": bool(_text(os.getenv("CREEM_API_KEY")) and _text(os.getenv("CREEM_WEBHOOK_SECRET")))
                and all(bool(_text(get_plan(plan_id).get("creem_product_id"))) for plan_id in PLAN_ORDER),
            },
        }

    def status(self) -> dict[str, Any]:
        stage = _text(phase_i_config(self.config_store, "stage", "preflight")) or "preflight"
        if stage not in PHASE_I_STAGES:
            stage = "preflight"
        source = self._source_context()
        health = build_rollout_health(self.config_store, self.acquisition_store)
        return {
            "phase": "I",
            "stage": stage,
            "rollout_enabled": _bool(phase_i_config(self.config_store, "rollout_enabled", False)),
            "production_source_id": _text(phase_i_config(self.config_store, "production_source_id", "")) or None,
            "additional_source_ids": _list(phase_i_config(self.config_store, "additional_source_ids", [])),
            "cohorts": {
                "gate_enabled": _bool(phase_i_config(self.config_store, "user_cohort_gate_enabled", False)),
                "internal_count": len(_list(phase_i_config(self.config_store, "internal_cohort_user_ids", []))),
                "selected_count": len(_list(phase_i_config(self.config_store, "selected_cohort_user_ids", []))),
            },
            "ceilings": {
                "global_requests": _int(phase_i_config(self.config_store, "global_request_ceiling", 100), 100),
                "cycle_requests": _int(phase_i_config(self.config_store, "cycle_request_ceiling", 16), 16),
                "cycle_credits": _int(phase_i_config(self.config_store, "cycle_credit_ceiling", 0), 0),
                "target_requests": dict(phase_i_config(self.config_store, "target_request_ceilings", {}) or {}),
                "target_credits": dict(phase_i_config(self.config_store, "target_credit_ceilings", {}) or {}),
            },
            "source": {
                "target": source.get("target"),
                "metrics": source.get("metrics"),
            },
            "rollout_history": _history(self.config_store),
            "gates": self._gates(),
            "health": health,
        }

    def configure(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        manifest_ids = {str(item["target_id"]) for item in load_phase_a_manifest()}
        source_id = _text(payload.get("production_source_id"))
        if source_id and source_id not in manifest_ids:
            raise ValueError(f"Unknown production source '{source_id}'.")
        additional = _list(payload.get("additional_source_ids"))
        unknown = [item for item in additional if item not in manifest_ids]
        if unknown:
            raise ValueError("Unknown additional source(s): " + ", ".join(unknown))
        global_requests = _int(payload.get("global_request_ceiling"), _int(phase_i_config(self.config_store, "global_request_ceiling", 100), 100))
        cycle_requests = _int(payload.get("cycle_request_ceiling"), _int(phase_i_config(self.config_store, "cycle_request_ceiling", 16), 16))
        if cycle_requests > global_requests:
            raise ValueError("cycle_request_ceiling cannot exceed global_request_ceiling.")
        values = {
            "production_source_id": source_id,
            "additional_source_ids": additional,
            "internal_cohort_user_ids": _list(payload.get("internal_cohort_user_ids")),
            "selected_cohort_user_ids": _list(payload.get("selected_cohort_user_ids")),
            "user_cohort_gate_enabled": _bool(payload.get("user_cohort_gate_enabled"), _bool(phase_i_config(self.config_store, "user_cohort_gate_enabled", False))),
            "global_request_ceiling": global_requests,
            "cycle_request_ceiling": cycle_requests,
            "cycle_credit_ceiling": _int(payload.get("cycle_credit_ceiling"), _int(phase_i_config(self.config_store, "cycle_credit_ceiling", 0), 0)),
            "target_request_ceilings": dict(payload.get("target_request_ceilings") or phase_i_config(self.config_store, "target_request_ceilings", {}) or {}),
            "target_credit_ceilings": dict(payload.get("target_credit_ceilings") or phase_i_config(self.config_store, "target_credit_ceilings", {}) or {}),
            "stale_catalog_alert_hours": max(1, _int(payload.get("stale_catalog_alert_hours"), _int(phase_i_config(self.config_store, "stale_catalog_alert_hours", 48), 48))),
            "failed_cycle_alert_threshold": max(1, _int(payload.get("failed_cycle_alert_threshold"), _int(phase_i_config(self.config_store, "failed_cycle_alert_threshold", 1), 1))),
            "failed_cycle_alert_window_hours": max(1, _int(payload.get("failed_cycle_alert_window_hours"), _int(phase_i_config(self.config_store, "failed_cycle_alert_window_hours", 48), 48))),
        }
        for name, value in values.items():
            _set_config(self.config_store, f"acquisition.phase_i.{name}", value)
        for name in _EVIDENCE_KEYS:
            if name in payload:
                _set_config(self.config_store, f"acquisition.phase_i.{name}", _bool(payload.get(name)))
        return self.status()

    def advance(self, requested_stage: str) -> dict[str, Any]:
        requested = _text(requested_stage)
        if requested not in PHASE_I_STAGES:
            raise ValueError(f"Unknown Phase I stage '{requested_stage}'.")
        current = _text(phase_i_config(self.config_store, "stage", "preflight")) or "preflight"
        if current not in PHASE_I_STAGES:
            current = "preflight"
        if PHASE_I_STAGES.index(requested) != PHASE_I_STAGES.index(current) + 1:
            raise ValueError(f"Phase I must advance one stage at a time from '{current}'.")
        gates = self._gates()
        requirements = {
            "one_source_production": ("earlier_phases_accepted", "source_configured", "source_measured", "source_productive", "cost_measured", "apply_quality_verified"),
            "staging_publication": ("source_fresh",),
            "internal_cohort": ("staging_ready", "catalog_inspection_approved", "internal_cohort_configured", "cohort_gate_enabled"),
            "selected_cohort": ("internal_cohort_configured", "selected_cohort_configured", "cohort_gate_enabled"),
            "source_expansion": ("selected_cohort_configured", "cohort_gate_enabled"),
            "daily_scheduler": ("source_productive", "selected_cohort_configured", "cost_measured", "cohort_gate_enabled"),
            "pro_checkout": ("creem_products_configured",),
            "complete": ("selected_cohort_configured", "source_productive", "creem_products_configured"),
        }.get(requested, ())
        missing = [name for name in requirements if not bool(gates.get(name, {}).get("passed"))]
        if missing:
            raise ValueError("Phase I stage blocked: " + ", ".join(missing))
        _set_config(self.config_store, "acquisition.phase_i.stage", requested)
        _set_config(self.config_store, "acquisition.phase_i.rollout_enabled", True)
        history = _history(self.config_store)
        history.append(
            {
                "event": "stage_advanced",
                "from_stage": current,
                "stage": requested,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "passed_gates": [name for name, value in gates.items() if bool(value.get("passed"))],
            }
        )
        _set_config(self.config_store, "acquisition.phase_i.rollout_history", history)
        if requested == "one_source_production":
            source_id = _text(phase_i_config(self.config_store, "production_source_id", ""))
            _set_config(self.config_store, f"acquisition.phase_a.target.{source_id}.enabled", True)
            source_manifest = next(
                (item for item in load_phase_a_manifest() if _text(item.get("target_id")) == source_id),
                {},
            )
            if _text(source_manifest.get("target_kind")) == "ats_connector_validation":
                _set_config(self.config_store, "acquisition.phase_a.connector_validation_enabled", True)
        if requested == "staging_publication":
            _set_config(self.config_store, "acquisition.phase_b.staging_publication_enabled", True)
        if requested == "source_expansion":
            for source_id in _list(phase_i_config(self.config_store, "additional_source_ids", [])):
                _set_config(self.config_store, f"acquisition.phase_a.target.{source_id}.enabled", True)
        if requested == "daily_scheduler":
            _set_config(self.config_store, "acquisition.phase_i.production_publication_enabled", True)
            _set_config(self.config_store, "acquisition.phase_a.kill_switch", False)
            _set_config(self.config_store, "acquisition.phase_a.global_enabled", True)
            _set_config(self.config_store, "acquisition.phase_a.scheduler_enabled", True)
            _set_config(self.config_store, "acquisition.phase_a.publication_enabled", True)
            _set_config(self.config_store, "acquisition.phase_a.global_request_ceiling", phase_i_config(self.config_store, "global_request_ceiling", 100))
            _set_config(self.config_store, "acquisition.phase_a.cycle_request_ceiling", phase_i_config(self.config_store, "cycle_request_ceiling", 16))
            _set_config(self.config_store, "acquisition.phase_a.cycle_credit_ceiling", phase_i_config(self.config_store, "cycle_credit_ceiling", 0))
        if requested == "pro_checkout":
            _set_config(self.config_store, "acquisition.phase_i.checkout_gate_enabled", True)
        self._emit("production_rollout_advanced", stage=requested)
        return self.status()


__all__ = [
    "PHASE_I_DEFAULT_CONFIG",
    "PHASE_I_STAGES",
    "ProductionRolloutService",
    "build_rollout_health",
    "catalog_user_access",
    "phase_i_config",
]
