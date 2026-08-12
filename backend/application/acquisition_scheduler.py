from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from backend.acquisition.manifest import load_phase_a_manifest
from backend.acquisition.network_policy import (
    AcquisitionNetworkPolicyError,
    hostname_for_url,
    require_phase_a_network_permission,
)
from backend.connectors.ats_router import fetch_ats_snapshot
from backend.connectors.ats_expansions import EXPANSION_CONNECTORS
from backend.connectors.bounded_probe import fetch_bounded_probe
from backend.connectors.generic_jsonld import fetch_generic_snapshot
from backend.acquisition.phase_b import PHASE_B_DEFAULT_CONFIG, normalize_phase_b_jobs
from backend.acquisition.phase_g import portal_audit_gate
from backend.application.production_rollout import build_rollout_health, phase_i_config, private_test_deployment_enabled


LOGGER = logging.getLogger("backend.acquisition.phase_a")


class AcquisitionDispatchBlockedError(RuntimeError):
    """The request was reserved but the pre-dispatch policy rejected it."""


class AcquisitionUncertainOutcomeError(RuntimeError):
    """An external call may have occurred and requires explicit recovery."""


class AcquisitionRecoveryRequiredError(RuntimeError):
    """Durable request state exists but a later persistence boundary failed."""


PHASE_A_DEFAULT_CONFIG: dict[str, Any] = {
    "scheduler_enabled": False,
    "kill_switch": True,
    "global_enabled": False,
    "connector_validation_enabled": False,
    "publication_enabled": False,
    "allow_proxy": False,
    "ai_enrichment_enabled": False,
    "global_request_ceiling": 100,
    "cycle_request_ceiling": 16,
    "cycle_credit_ceiling": 0,
}

PHASE_A_PRODUCTION_CONFIG: dict[str, Any] = {
    **PHASE_A_DEFAULT_CONFIG,
    "scheduler_enabled": True,
    "kill_switch": False,
    "global_enabled": True,
    "connector_validation_enabled": True,
    "publication_enabled": True,
    "allow_proxy": True,
}

PHASE_B_PRODUCTION_CONFIG: dict[str, Any] = {
    **PHASE_B_DEFAULT_CONFIG,
    "controlled_validation_enabled": True,
    "staging_publication_enabled": True,
    "promotion_enabled": True,
}


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on", "enabled"}


def _as_int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _admin_scope_for_target(target: Mapping[str, Any]) -> dict[str, Any]:
    config = target.get("config")
    return dict(config.get("admin_scope") or {}) if isinstance(config, Mapping) else {}


def _admin_scope_matches(job: Mapping[str, Any], scope: Mapping[str, Any]) -> bool:
    """Apply only explicit, source-observed filters; missing facts stay unknown."""

    if bool(scope.get("full_source_import")):
        return True
    searchable = " ".join(
        str(job.get(key) or "")
        for key in ("title", "description", "full_description", "department", "category", "job_category", "function")
    ).casefold()
    keywords = [str(item).strip().casefold() for item in (scope.get("keywords") or []) if str(item).strip()]
    if keywords and not all(keyword in searchable for keyword in keywords):
        return False
    for field in ("department", "category"):
        value = str(scope.get(field) or "").strip().casefold()
        if value and value not in searchable:
            return False
    location = " ".join(str(job.get(key) or "") for key in ("location", "location_raw", "city", "country")).casefold()
    cities = [str(item).strip().casefold() for item in (scope.get("cities") or []) if str(item).strip()]
    if cities and not any(city in location for city in cities):
        return False
    country = str(scope.get("country") or "").strip().casefold()
    if country and country not in location:
        return False
    if bool(scope.get("remote")):
        work_style = " ".join(str(job.get(key) or "") for key in ("work_arrangement", "workplace", "remote_type", "location")).casefold()
        if "remote" not in work_style and "home office" not in work_style:
            return False
    return True


@dataclass(slots=True)
class PhaseAAcquisitionScheduler:
    repositories: Any
    event_emitter: Callable[..., None] | None = None
    requester: Callable[..., Any] | None = None
    failure_injector: Callable[[str], None] | None = None
    lease_owner: str = "system-acquisition"
    lease_seconds: int = 300

    def _config(self, key: str, default: Any = None) -> Any:
        store = getattr(self.repositories, "config_store", None)
        getter = getattr(store, "get_value", None)
        if not callable(getter):
            return default
        return getter(key, default)

    def _phase_a_config(self, name: str) -> Any:
        if private_test_deployment_enabled():
            forced_values = {
                "scheduler_enabled": False,
                "kill_switch": True,
                "global_enabled": False,
                "connector_validation_enabled": False,
                "publication_enabled": False,
                "allow_proxy": False,
                "ai_enrichment_enabled": False,
            }
            if name.startswith("target."):
                return False
            if name in forced_values:
                return forced_values[name]
        if name.startswith("target."):
            production_default = str(os.getenv("RUNR_ENV") or "").strip().casefold() in {"prod", "production"}
            return self._config(f"acquisition.phase_a.{name}", production_default)
        production = str(os.getenv("RUNR_ENV") or "").strip().casefold() in {"prod", "production"}
        default = (PHASE_A_PRODUCTION_CONFIG if production else PHASE_A_DEFAULT_CONFIG)[name]
        return self._config(f"acquisition.phase_a.{name}", default)

    def _phase_b_config(self, name: str) -> Any:
        if private_test_deployment_enabled() and name in {
            "controlled_validation_enabled",
            "staging_publication_enabled",
            "promotion_enabled",
        }:
            return False
        production = str(os.getenv("RUNR_ENV") or "").strip().casefold() in {"prod", "production"}
        default = (PHASE_B_PRODUCTION_CONFIG if production else PHASE_B_DEFAULT_CONFIG)[name]
        return self._config(f"acquisition.phase_b.{name}", default)

    def _phase_i_config(self, name: str, default: Any = None) -> Any:
        return phase_i_config(getattr(self.repositories, "config_store", None), name, default)

    def _configured_manifest(self) -> list[dict[str, Any]]:
        manifest = load_phase_a_manifest()
        connector_validation_enabled = _as_bool(self._phase_a_config("connector_validation_enabled"))
        proxy_allowed = _as_bool(self._phase_a_config("allow_proxy"))
        rollout_enabled = _as_bool(self._phase_i_config("rollout_enabled", False))
        production_source_id = str(self._phase_i_config("production_source_id", "") or "").strip()
        additional_source_ids = {
            str(item).strip()
            for item in (self._phase_i_config("additional_source_ids", []) or [])
            if str(item).strip()
        }
        target_request_ceilings = dict(self._phase_i_config("target_request_ceilings", {}) or {})
        production_publication_enabled = _as_bool(self._phase_i_config("production_publication_enabled", False))
        for target in manifest:
            target_id = str(target["target_id"])
            target_enabled = _as_bool(self._phase_a_config(f"target.{target_id}.enabled"))
            if rollout_enabled and target_id not in {production_source_id, *additional_source_ids}:
                target_enabled = False
            disabled_reason = str(target.get("disabled_reason") or "phase_a_target_disabled_by_default")
            if target.get("target_kind") == "ats_connector_validation" and not connector_validation_enabled:
                target_enabled = False
                disabled_reason = "connector_validation_disabled_by_default"
            if str(target.get("request_mode") or "direct") != "direct" and not proxy_allowed:
                target_enabled = False
                disabled_reason = "proxy_permission_disabled_by_default"
            if target_id in target_request_ceilings:
                target["max_direct_requests"] = max(1, _as_int(target_request_ceilings[target_id], 1))
            if rollout_enabled:
                target["publication_enabled"] = bool(
                    production_publication_enabled
                    and target_enabled
                    and target_id in {production_source_id, *additional_source_ids}
                )
            elif target_enabled and str(os.getenv("RUNR_ENV") or "").strip().casefold() in {"prod", "production"}:
                target["publication_enabled"] = True
            target["enabled"] = target_enabled
            target["disabled_reason"] = "" if target_enabled else disabled_reason
        return manifest

    def _emit(self, event_name: str, **payload: Any) -> None:
        if not callable(self.event_emitter):
            return
        self.event_emitter(event_name, source="system_acquisition", payload=payload)

    def _failpoint(self, name: str) -> None:
        if callable(self.failure_injector):
            self.failure_injector(name)

    @staticmethod
    def _requester_is_fixture() -> bool:
        return bool(os.environ.get("PYTEST_CURRENT_TEST")) or str(os.environ.get("RUNR_ENV") or "").strip().casefold() in {
            "test",
            "testing",
        }

    def run_due_cycle(self, *, now: datetime | None = None, force: bool = False) -> dict[str, Any] | None:
        store = getattr(self.repositories, "acquisition_store", None)
        if store is None:
            return None
        recovered = store.recover_dispatching_requests()
        if recovered:
            cycle_ids = {str(item.get("cycle_id") or "") for item in recovered if item.get("cycle_id")}
            cycle_id = next(iter(cycle_ids), "")
            self._emit(
                "acquisition_recovery_required",
                cycle_id=cycle_id,
                recovered_requests=len(recovered),
            )
            report = store.get_cycle_report(cycle_id) if cycle_id else {"status": "recovery_required"}
            report["status"] = "recovery_required"
            report["recovered_requests"] = recovered
            return report
        if _as_bool(self._phase_a_config("kill_switch")):
            self._emit("acquisition_scheduler_kill_switch_blocked", reason="configured_kill_switch")
            return {"status": "kill_switch"}
        if not force and not _as_bool(self._phase_a_config("scheduler_enabled")):
            self._emit("acquisition_scheduler_disabled", reason="phase_a_scheduler_disabled")
            return {"status": "scheduler_disabled", "reason": "phase_a_scheduler_disabled"}
        if not _as_bool(self._phase_a_config("global_enabled")):
            self._emit("acquisition_scheduler_disabled", reason="phase_a_global_disabled")
            return {"status": "disabled", "reason": "phase_a_global_disabled"}
        if _as_bool(self._phase_a_config("ai_enrichment_enabled")):
            self._emit("acquisition_ai_enrichment_blocked", reason="phase_a_ai_enrichment_not_implemented")
            return {"status": "disabled", "reason": "phase_a_ai_enrichment_not_implemented"}

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        scheduled_at = current.isoformat()
        window_key = f"phase_a:{current.strftime('%Y-%m-%d')}"
        manifest = self._configured_manifest()
        store.ensure_targets(manifest)
        allow_recheck = _as_bool(self._config("acquisition.phase_a.allow_quarantined_recheck", False))
        targets = []
        for target in store.list_targets(include_disabled=False):
            if not allow_recheck and str(target.get("maturity_state") or "") in {"quarantined", "disabled"}:
                continue
            if not allow_recheck and str(target.get("target_kind") or "") == "employer_career_site":
                attempts = store.get_target_history(str(target["target_id"])).get("attempts") or []
                if len(attempts) >= _as_int(target.get("max_direct_requests"), 3):
                    continue
            targets.append(target)
            self._emit_stale_alert_if_needed(target)
        if not targets:
            self._emit("acquisition_scheduler_noop", reason="no_enabled_targets")
            return {"status": "no_op", "reason": "no_enabled_targets"}

        cycle = store.claim_due_cycle(
            window_key=window_key,
            lease_owner=self.lease_owner,
            scheduled_at=scheduled_at,
            lease_seconds=self.lease_seconds,
            force=force,
        )
        if cycle is None:
            self._emit("acquisition_scheduler_noop", reason="window_already_claimed", window_key=window_key)
            return None
        cycle_id = str(cycle["cycle_id"])
        self._emit("acquisition_cycle_claimed", cycle_id=cycle_id, window_key=window_key)
        global_request_ceiling = _as_int(self._phase_a_config("global_request_ceiling"), 100)
        cycle_request_ceiling = min(
            _as_int(self._phase_a_config("cycle_request_ceiling"), 16),
            global_request_ceiling,
        )
        forecast_requests = sum(min(_as_int(target.get("max_direct_requests"), 3), 1) for target in targets)
        store.set_cycle_forecast(cycle_id, requests=min(forecast_requests, cycle_request_ceiling), credits=0)
        store.ensure_cycle_tasks(cycle_id, targets)

        completed = 0
        failures = 0
        recovery_required = False
        recovery_reason = ""
        valid_target_ids: list[str] = []
        while True:
            task = store.claim_next_task(
                cycle_id=cycle_id,
                lease_owner=self.lease_owner,
                lease_seconds=self.lease_seconds,
            )
            if task is None:
                break
            target_id = str(task["target_id"])
            target = store.get_target(target_id)
            if completed >= cycle_request_ceiling:
                failures += 1
                store.complete_task(
                    str(task["task_id"]),
                    status="budget_exhausted",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code="cycle_request_ceiling",
                    error_message="Global Phase A cycle request ceiling reached.",
                )
                self._emit("acquisition_budget_exhausted", cycle_id=cycle_id, target_id=target_id)
                continue
            try:
                result = self._execute_target(cycle_id=cycle_id, task=task, target=target)
                completed += 1
                self._emit(
                    "acquisition_target_executed",
                    cycle_id=cycle_id,
                    target_id=target_id,
                    status=str(result.get("status") or ""),
                )
                if bool(result.get("valid_snapshot")) and bool(target.get("publication_enabled")):
                    valid_target_ids.append(target_id)
                if str(result.get("status") or "") in {"failed", "blocked", "budget_exhausted"}:
                    failures += 1
            except AcquisitionRecoveryRequiredError as exc:
                failures += 1
                recovery_required = True
                recovery_reason = str(exc)[:500]
                store.complete_task(
                    str(task["task_id"]),
                    status="recovery_required",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code="recovery_required",
                    error_message=recovery_reason,
                )
                self._emit("acquisition_recovery_required", cycle_id=cycle_id, target_id=target_id)
                break
            except AcquisitionUncertainOutcomeError as exc:
                failures += 1
                recovery_required = True
                recovery_reason = str(exc)[:500]
                store.complete_task(
                    str(task["task_id"]),
                    status="recovery_required",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code="uncertain_external_outcome",
                    error_message=recovery_reason,
                )
                self._emit("acquisition_recovery_required", cycle_id=cycle_id, target_id=target_id)
                break
            except AcquisitionDispatchBlockedError as exc:
                failures += 1
                store.complete_task(
                    str(task["task_id"]),
                    status="blocked",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code="dispatch_blocked",
                    error_message=str(exc)[:500],
                )
                self._emit("acquisition_source_blocked", cycle_id=cycle_id, target_id=target_id)
            except Exception as exc:
                failures += 1
                LOGGER.exception("phase_a_target_failed", extra={"target_id": target_id, "cycle_id": cycle_id})
                store.complete_task(
                    str(task["task_id"]),
                    status="failed",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code=type(exc).__name__.casefold(),
                    error_message=str(exc)[:500],
                )
                self._emit(
                    "acquisition_source_failed", cycle_id=cycle_id, target_id=target_id, reason=type(exc).__name__
                )

        if recovery_required:
            store.complete_cycle(
                cycle_id,
                status="recovery_required",
                error_code="recovery_required",
                error_message=recovery_reason or "Phase A cycle requires explicit recovery.",
            )
            self._emit(
                "acquisition_cycle_recovery_required",
                cycle_id=cycle_id,
                reason=recovery_reason or "explicit_recovery_required",
            )
            return store.get_cycle_report(cycle_id)

        publication_id = ""
        publication_enabled = _as_bool(self._phase_a_config("publication_enabled"))
        if publication_enabled and valid_target_ids:
            try:
                self._failpoint("during_publication_creation")
                publication_id = store.publish_valid_snapshot(
                    cycle_id=cycle_id,
                    valid_target_ids=valid_target_ids,
                    origin="scheduled",
                    created_by="system",
                    scheduled_run_id=cycle_id,
                )
            except BaseException as exc:
                store.complete_cycle(
                    cycle_id,
                    status="recovery_required",
                    error_code="publication_recovery_required",
                    error_message=str(exc)[:500],
                )
                self._emit(
                    "acquisition_cycle_recovery_required",
                    cycle_id=cycle_id,
                    reason="publication_recovery_required",
                )
                raise
        cycle_status = "degraded" if failures else "completed"
        store.complete_cycle(cycle_id, status=cycle_status, publication_id=publication_id)
        self._emit(
            "acquisition_cycle_completed",
            cycle_id=cycle_id,
            status=cycle_status,
            completed_targets=completed,
            failed_targets=failures,
        )
        if failures:
            self._emit("acquisition_catalog_degraded", cycle_id=cycle_id, failed_targets=failures)
        health = build_rollout_health(getattr(self.repositories, "config_store", None), store)
        for alert in health.get("alerts") or []:
            self._emit("production_rollout_alert", cycle_id=cycle_id, **dict(alert))
        return store.get_cycle_report(cycle_id)

    def recover_cycle(self) -> dict[str, Any] | None:
        """Protected admin recovery entry point; kill switch still wins."""

        return self.run_due_cycle(force=True)

    def run_controlled_import(self, import_payload: Mapping[str, Any], *, worker_id: str = "runr-worker") -> dict[str, Any]:
        """Execute one durable admin import through the normal worker boundary.

        Publication is deliberately excluded here. The review service creates a
        staging snapshot only after administrator decisions, and a separate
        explicit publish action moves the public head.
        """

        store = getattr(self.repositories, "acquisition_store", None)
        if store is None:
            raise ValueError("Admin imports require sqlite/Turso acquisition storage.")
        # Admin imports are governed by the separate admin-import switch at the
        # application boundary. The Phase-A kill switch protects the scheduled
        # acquisition loop and must not block an explicitly requested admin run.
        manifest = {str(item["target_id"]): dict(item) for item in load_phase_a_manifest()}
        source_ids = [str(item).strip() for item in (import_payload.get("source_ids") or []) if str(item).strip()]
        scope = dict(import_payload.get("scope") or {})
        plan = dict(import_payload.get("plan") or {})
        targets: list[dict[str, Any]] = []
        for source_id in source_ids:
            if source_id not in manifest:
                raise KeyError(f"Unsupported import source '{source_id}'.")
            target = dict(manifest[source_id])
            connector = str(target.get("connector") or "").casefold()
            target["enabled"] = True
            target["publication_enabled"] = False
            target["disabled_reason"] = ""
            target["config"] = {
                **dict(target.get("config") or {}),
                "admin_import_id": str(import_payload.get("import_id") or ""),
                "admin_import_method": (
                    "direct"
                    if connector in {"greenhouse", "lever", *EXPANSION_CONNECTORS, "generic_jsonld"}
                    else "web"
                ),
                "admin_import_allow_proxy": bool(plan.get("admin_import_allow_proxy")),
                "admin_scope": scope,
            }
            if connector not in {"greenhouse", "lever", *EXPANSION_CONNECTORS, "generic_jsonld"}:
                target["connector"] = "company_career_sites"
                target["request_mode"] = "scrapeops"
            targets.append(target)
        store.ensure_targets(targets)
        now = datetime.now(timezone.utc)
        import_id = str(import_payload.get("import_id") or "")
        cycle = store.claim_due_cycle(
            window_key=f"admin_import:{str(import_payload.get('idempotency_key') or import_id)}",
            lease_owner=worker_id,
            scheduled_at=now.isoformat(),
            # A single official ATS snapshot can take longer than the default
            # five-minute scheduler lease to project into remote Turso. Keep
            # recovery available, but do not let a healthy long transaction be
            # reclaimed by another writer at the five-minute boundary.
            lease_seconds=max(self.lease_seconds, 1800),
            force=False,
        )
        if cycle is None:
            existing = store.list_cycles(limit=100, offset=0)
            for item in existing:
                if str(item.get("window_key") or "") == f"admin_import:{str(import_payload.get('idempotency_key') or import_id)}":
                    return store.get_cycle_report(str(item["cycle_id"]))
            return {"status": "already_claimed", "import_id": import_id}
        cycle_id = str(cycle["cycle_id"])
        store.attach_job_import_cycle(import_id, cycle_id)
        store.set_cycle_forecast(
            cycle_id,
            requests=min(
                max(1, int(plan.get("maximum_requests") or len(targets))),
                max(1, _as_int(scope.get("max_requests"), 100)),
            ),
            credits=max(0, int(plan.get("maximum_credits") or 0)),
        )
        store.ensure_cycle_tasks(cycle_id, targets)
        failures = 0
        for _ in targets:
            task = store.claim_next_task(cycle_id=cycle_id, lease_owner=worker_id, lease_seconds=max(self.lease_seconds, 1800))
            if task is None:
                break
            target = store.get_target(str(task["target_id"]))
            try:
                result = self._execute_target(cycle_id=cycle_id, task=task, target=target)
                if str(result.get("status") or "") in {"failed", "blocked", "budget_exhausted"}:
                    failures += 1
            except AcquisitionRecoveryRequiredError as exc:
                failures += 1
                store.complete_task(
                    str(task["task_id"]),
                    status="recovery_required",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code="recovery_required",
                    error_message=str(exc)[:500],
                )
                break
            except AcquisitionUncertainOutcomeError as exc:
                failures += 1
                store.complete_task(
                    str(task["task_id"]),
                    status="recovery_required",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code="uncertain_external_outcome",
                    error_message=str(exc)[:500],
                )
                break
            except AcquisitionDispatchBlockedError as exc:
                failures += 1
                store.complete_task(
                    str(task["task_id"]),
                    status="blocked",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code="dispatch_blocked",
                    error_message=str(exc)[:500],
                )
            except Exception as exc:
                failures += 1
                store.complete_task(
                    str(task["task_id"]),
                    status="failed",
                    result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                    error_code=type(exc).__name__.casefold(),
                    error_message=str(exc)[:500],
                )
        status = "degraded" if failures else "completed"
        store.complete_cycle(cycle_id, status=status)
        return store.get_cycle_report(cycle_id)

    def validate_target(self, target_id: str, *, validation_key: str = "") -> dict[str, Any]:
        """Run exactly one explicitly requested Phase B target.

        This path is admin/worker-only at the API boundary.  It never consults
        the daily scheduler window and never loops over the manifest.
        """

        store = getattr(self.repositories, "acquisition_store", None)
        if store is None:
            raise ValueError("Phase B validation requires sqlite storage support.")
        if _as_bool(self._phase_a_config("kill_switch")):
            return {"status": "kill_switch", "target_id": str(target_id)}
        if not _as_bool(self._phase_b_config("controlled_validation_enabled")):
            return {"status": "disabled", "reason": "phase_b_controlled_validation_disabled"}
        manifest = {str(item["target_id"]): dict(item) for item in load_phase_a_manifest()}
        normalized_target_id = str(target_id or "").strip()
        if normalized_target_id not in manifest:
            raise KeyError(f"Phase B target '{target_id}' is not in the server-owned manifest.")
        target = manifest[normalized_target_id]
        # A controlled validation is a single explicit source run.  The source
        # is enabled for this run only; publication remains staging-only.
        target["enabled"] = True
        target["publication_enabled"] = False
        target["disabled_reason"] = ""
        store.ensure_targets([target])
        target = store.get_target(normalized_target_id)
        now = datetime.now(timezone.utc)
        run_key = str(validation_key or f"{now.isoformat()}:{normalized_target_id}")
        cycle = store.claim_due_cycle(
            window_key=f"phase_b:{normalized_target_id}:{run_key}",
            lease_owner=self.lease_owner,
            scheduled_at=now.isoformat(),
            lease_seconds=self.lease_seconds,
            force=False,
        )
        if cycle is None:
            return {"status": "already_claimed", "target_id": normalized_target_id}
        cycle_id = str(cycle["cycle_id"])
        store.set_cycle_forecast(cycle_id, requests=1, credits=0)
        store.ensure_cycle_tasks(cycle_id, [target])
        task = store.claim_next_task(cycle_id=cycle_id, lease_owner=self.lease_owner, lease_seconds=self.lease_seconds)
        if task is None:
            store.complete_cycle(cycle_id, status="failed", error_code="task_claim_failed")
            return store.get_cycle_report(cycle_id)
        try:
            result = self._execute_target(cycle_id=cycle_id, task=task, target=target)
            publication_id = ""
            if bool(result.get("valid_snapshot")) and _as_bool(self._phase_b_config("staging_publication_enabled")):
                publication_id = store.publish_staging_snapshot(
                    cycle_id=cycle_id,
                    valid_target_ids=[normalized_target_id],
                    origin="scheduled",
                    created_by="system",
                    scheduled_run_id=cycle_id,
                )
            cycle_status = "degraded" if str(result.get("status") or "") in {"failed", "blocked"} else "completed"
            store.complete_cycle(cycle_id, status=cycle_status, publication_id=publication_id)
        except AcquisitionRecoveryRequiredError as exc:
            store.complete_task(
                str(task["task_id"]),
                status="recovery_required",
                result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                error_code="recovery_required",
                error_message=str(exc)[:500],
            )
            store.complete_cycle(cycle_id, status="recovery_required", error_code="recovery_required", error_message=str(exc)[:500])
        except AcquisitionUncertainOutcomeError as exc:
            store.complete_task(
                str(task["task_id"]),
                status="recovery_required",
                result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                error_code="uncertain_external_outcome",
                error_message=str(exc)[:500],
            )
            store.complete_cycle(cycle_id, status="recovery_required", error_code="uncertain_external_outcome", error_message=str(exc)[:500])
        except AcquisitionDispatchBlockedError as exc:
            store.complete_task(
                str(task["task_id"]),
                status="blocked",
                result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                error_code="dispatch_blocked",
                error_message=str(exc)[:500],
            )
            store.complete_cycle(cycle_id, status="blocked", error_code="dispatch_blocked", error_message=str(exc)[:500])
        except Exception as exc:
            LOGGER.exception("phase_b_target_failed", extra={"target_id": normalized_target_id, "cycle_id": cycle_id})
            store.complete_task(
                str(task["task_id"]),
                status="failed",
                result={"complete_snapshot": False, "valid_snapshot": False, "credible_evidence": False},
                error_code=type(exc).__name__.casefold(),
                error_message=str(exc)[:500],
            )
            store.complete_cycle(cycle_id, status="failed", error_code=type(exc).__name__.casefold(), error_message=str(exc)[:500])
        return store.get_cycle_report(cycle_id)

    def _execute_target(self, *, cycle_id: str, task: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
        store = self.repositories.acquisition_store
        target_id = str(target["target_id"])
        task_id = str(task["task_id"])
        portal_audit = portal_audit_gate(target)
        if portal_audit.get("required") and not portal_audit.get("approved"):
            raise AcquisitionDispatchBlockedError(
                "phase_g_portal_audit_not_passed:" + ",".join(portal_audit.get("missing") or [])
            )
        idempotency_key = f"phase_a:{cycle_id}:{target_id}:attempt:{int(task.get('attempt_count') or 1)}"
        phase_i_target_credits = dict(self._phase_i_config("target_credit_ceilings", {}) or {})
        configured_credit_limits = [
            _as_int(self._phase_a_config("cycle_credit_ceiling"), 0),
            _as_int(phase_i_target_credits.get(target_id), 0),
        ]
        credit_limits = [limit for limit in configured_credit_limits if limit > 0]
        request = store.reserve_request(
            cycle_id=cycle_id,
            task_id=task_id,
            target_id=target_id,
            request_url=str(target["request_url"]),
            method="GET",
            mode=str(target.get("request_mode") or "direct"),
            request_kind="listing_probe" if target.get("target_kind") == "employer_career_site" else "ats_listing",
            idempotency_key=idempotency_key,
            credits_estimated=0,
            request_limit=_as_int(target.get("max_direct_requests"), 3),
            credit_limit=min(credit_limits) if credit_limits else 0,
        )
        request_id = str(request["request_id"])
        state_before = str(target.get("maturity_state") or "unproven")
        dispatch_started = False
        request_persisted = False
        try:
            self._failpoint("after_durable_dispatch")
            request_mode = str(target.get("request_mode") or "direct").casefold()
            target_config = dict(target.get("config") or {})
            admin_import = bool(str(target_config.get("admin_import_id") or "").strip())
            if request_mode != "direct" and not (
                admin_import
                and (
                    _as_bool(self._config("acquisition.admin_imports.allow_proxy", False))
                    or _as_bool(target_config.get("admin_import_allow_proxy"))
                )
            ):
                raise AcquisitionNetworkPolicyError("phase_a_request_mode_not_permitted")
            allowed_hosts = {
                hostname_for_url(str(target.get("request_url") or "")),
                hostname_for_url(str(target.get("canonical_target_url") or "")),
            }
            configured_hosts = target.get("official_employer_hosts") or target_config.get("official_employer_hosts") or []
            if isinstance(configured_hosts, (list, tuple, set)):
                allowed_hosts.update(
                    hostname_for_url(f"https://{str(host).strip()}")
                    for host in configured_hosts
                    if str(host).strip()
                )
            if request_mode == "direct":
                require_phase_a_network_permission(
                    request_url=str(target["request_url"]),
                    canonical_url=str(target.get("canonical_target_url") or target["request_url"]),
                    requester_injected=self.requester is not None and self._requester_is_fixture(),
                    allowed_hosts=allowed_hosts,
                )
            store.mark_request_dispatching(request_id)
            self._failpoint("before_dispatch")
            dispatch_started = True
            started = time.perf_counter()
            connector = str(target.get("connector") or "")
            usage_events: list[dict[str, Any]] = []
            if connector in {"greenhouse", "lever"}:
                fetched = fetch_ats_snapshot(
                    str(target.get("canonical_target_url") or target["request_url"]),
                    connector,
                    requester=self.requester,
                    max_pages=max(1, _as_int(_admin_scope_for_target(target).get("max_pages"), 1)),
                )
            elif connector in EXPANSION_CONNECTORS:
                scope = _admin_scope_for_target(target)
                fetched = fetch_ats_snapshot(
                    str(target.get("canonical_target_url") or target["request_url"]),
                    connector,
                    requester=self.requester,
                    enabled=True,
                    max_requests=max(1, _as_int(target.get("max_direct_requests"), 1)),
                    max_pages=max(1, _as_int(scope.get("max_pages"), 1)),
                    max_retries=max(0, min(2, _as_int(target_config.get("max_retries"), 0))),
                    page_size=max(1, min(100, _as_int(target_config.get("page_size"), 100))),
                )
            elif connector == "generic_jsonld":
                scope = _admin_scope_for_target(target)
                fetched = fetch_generic_snapshot(
                    str(target.get("request_url") or target.get("canonical_target_url") or ""),
                    requester=self.requester,
                    max_job_links=max(1, min(25, _as_int(scope.get("max_pages"), 6))),
                    allowed_hosts=allowed_hosts,
                )
            elif connector == "company_career_sites":
                from backend.connectors.company_career_sites import scrape_company_career_sites

                scope = _admin_scope_for_target(target)
                site = {
                    "company_name": str(target.get("display_name") or target_id),
                    "url": str(target.get("canonical_target_url") or target.get("request_url") or ""),
                }
                try:
                    jobs, source_log = scrape_company_career_sites(
                        company_sites=[site],
                        source_type="company",
                        keywords=scope.get("keywords") or [],
                        target_country_codes=[scope.get("country")] if scope.get("country") else [],
                        target_cities=scope.get("cities") or [],
                        allow_foreign_entrypoints=bool(target_config.get("admin_import_id")),
                        max_sites_per_run=1,
                        max_job_links_per_site=max(1, _as_int(scope.get("max_pages"), 20) * 25),
                        run_credit_budget=max(0, _as_int(scope.get("max_credits"), 0)),
                        usage_callback=usage_events.append,
                    )
                    failures = list(source_log.get("errors") or []) if isinstance(source_log, Mapping) else []
                    fetched = {
                        "jobs": list(jobs or []),
                        "status": "completed" if not failures else "degraded",
                        "status_code": 200 if not failures else 207,
                        "complete_snapshot": not failures,
                        "credible_evidence": bool(jobs) or not failures,
                        "request_url": str(target.get("request_url") or ""),
                        "resolved_url": str(target.get("canonical_target_url") or ""),
                        "source_log": source_log,
                    }
                except Exception as exc:
                    fetched = {
                        "jobs": [],
                        "status": "failed",
                        "status_code": 0,
                        "complete_snapshot": False,
                        "credible_evidence": False,
                        "request_url": str(target.get("request_url") or ""),
                        "error": str(exc),
                        "source_log": {"errors": [str(exc)]},
                    }
            else:
                fetched = fetch_bounded_probe(str(target["request_url"]), requester=self.requester)
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            self._failpoint("after_response_before_result_persistence")
            resolved_url = str(fetched.get("resolved_url") or fetched.get("request_url") or target["request_url"])
            resolved_host = hostname_for_url(resolved_url)
            if resolved_host not in allowed_hosts:
                raise AcquisitionNetworkPolicyError("phase_a_redirect_hostname_not_allowlisted")
            # Scope filters are intentionally retained in the import record and
            # applied by the server-side review query. This keeps every source
            # observation visible to the administrator, including jobs whose
            # location or category is unknown.
            raw_jobs = list(fetched.get("jobs") or [])
            normalized = normalize_phase_b_jobs(raw_jobs, target)
            jobs = list(normalized.get("accepted") or [])
            rejections = list(normalized.get("rejected") or [])
            quality_warnings = list(dict.fromkeys(
                str(warning)
                for job in jobs
                for warning in (job.get("quality_warnings") or [])
                if str(warning).strip()
            ))
            raw_external_ids = [
                str(item.get("job_id") or item.get("external_job_id") or item.get("id") or "").strip()
                for item in raw_jobs
            ]
            distinct_external_ids = sorted({item for item in raw_external_ids if item})
            source_reported_count = fetched.get("source_reported_count")
            try:
                source_reported_count = int(source_reported_count) if source_reported_count not in (None, "") else None
            except (TypeError, ValueError):
                source_reported_count = None
            reconciliation = {
                "schema_version": "batch_reconciliation_v1",
                "source_reported_job_count": source_reported_count,
                "observed_rows": len(raw_jobs),
                "distinct_external_job_ids": len(distinct_external_ids),
                "active_source_states": {},
                "new_canonical_jobs": 0,
                "updated_canonical_jobs": 0,
                "unchanged_jobs": 0,
                "duplicates": len(raw_jobs) - len(distinct_external_ids),
                "rejections": len(rejections),
                "missing_jobs": max(0, source_reported_count - len(distinct_external_ids)) if source_reported_count is not None else None,
                "unexplained_count_difference": abs(source_reported_count - len(distinct_external_ids)) if source_reported_count is not None else None,
                "source_reported_count_available": source_reported_count is not None,
            }
            complete_snapshot = bool(fetched.get("complete_snapshot"))
            credible_evidence = bool(fetched.get("credible_evidence"))
            valid_snapshot = complete_snapshot and credible_evidence
            status = str(fetched.get("status") or "completed")
            request_status = "completed" if status == "completed" else status
            store.complete_request(
                request_id,
                status=request_status,
                provider_status=_as_int(fetched.get("status_code"), 0),
                credits_actual=sum(int(item.get("runner_credits") or item.get("native_credits") or 0) for item in usage_events),
                jobs_returned=len(raw_jobs),
                resolved_url=resolved_url,
                latency_ms=latency_ms,
                detail={
                    "evidence": str(fetched.get("evidence") or ""),
                    "redirected": bool(fetched.get("redirected")),
                    "resolved_ats": str(fetched.get("resolved_ats") or ""),
                    "accepted_jobs": len(jobs),
                    "rejected_jobs": len(rejections),
                    "rejections": rejections,
                    "reconciliation": reconciliation,
                    "quality_warnings": quality_warnings,
                    "pages_fetched": int(fetched.get("pages_fetched") or 1),
                    "usage_events": usage_events,
                    "source_log": fetched.get("source_log") or {},
                },
                error_code="" if status == "completed" else status,
                error_message=str(fetched.get("error") or "")[:500],
            )
            request_persisted = True
            store.record_job_rejections(
                request_id=request_id,
                cycle_id=cycle_id,
                task_id=task_id,
                target_id=target_id,
                rejections=rejections,
            )
            self._failpoint("during_observation_persistence")
            counts = store.ingest_snapshot(
                cycle_id=cycle_id,
                task_id=task_id,
                target_id=target_id,
                jobs=jobs,
                complete_snapshot=complete_snapshot,
                valid_snapshot=valid_snapshot,
            )
            counts["rejected"] = int(counts.get("rejected") or 0) + len(rejections)
            reconciliation.update(
                {
                    "new_canonical_jobs": int(counts.get("new") or 0),
                    "updated_canonical_jobs": int(counts.get("updated") or 0),
                    "unchanged_jobs": int(counts.get("unchanged") or 0),
                    "duplicates": int(counts.get("duplicates") or 0) + max(0, len(raw_jobs) - len(distinct_external_ids)),
                    "rejections": int(counts.get("rejected") or 0),
                    "active_source_states": store.get_source_state_summary(target_id),
                }
            )
            attempts = store.get_target_history(target_id).get("attempts") or []
            attempt_number = len(attempts) + 1
            if jobs:
                state_after = "productive" if connector in {"greenhouse", "lever"} else "candidate"
                streak = 0
            elif credible_evidence:
                # A credible empty listing is useful source evidence, but it
                # is not productive output and must not reset yield telemetry.
                state_after = state_before if state_before in {"candidate", "productive"} else "candidate"
                streak = int(target.get("zero_yield_streak") or 0) + 1
                if attempt_number >= _as_int(target.get("max_direct_requests"), 3):
                    state_after = "quarantined"
            elif attempt_number >= _as_int(target.get("max_direct_requests"), 3):
                state_after = "quarantined"
                streak = int(target.get("zero_yield_streak") or 0) + 1
            else:
                state_after = state_before
                streak = int(target.get("zero_yield_streak") or 0) + (1 if not jobs else 0)
            store.update_target_state(
                target_id,
                maturity_state=state_after,
                reason=str(fetched.get("evidence") or status),
                zero_yield_streak=streak,
                successful_at=datetime.now(timezone.utc).isoformat() if jobs else "",
            )
            store.record_attempt(
                task_id=task_id,
                cycle_id=cycle_id,
                target_id=target_id,
                attempt_number=attempt_number,
                status=status,
                complete_snapshot=complete_snapshot,
                valid_snapshot=valid_snapshot,
                credible_evidence=credible_evidence,
                request_count=1,
                credits_actual=0,
                jobs_found=len(jobs),
                state_before=state_before,
                state_after=state_after,
                reason=str(fetched.get("evidence") or status),
                error_code="" if status == "completed" else status,
                error_message=str(fetched.get("error") or "")[:500],
            )
            result = {
                **counts,
                "status": status,
                "complete_snapshot": complete_snapshot,
                "valid_snapshot": valid_snapshot,
                "credible_evidence": credible_evidence,
                "requests_avoided": 0,
                "credits_avoided": 0,
                "reconciliation": reconciliation,
                "quality_warnings": quality_warnings,
            }
            store.complete_task(
                task_id,
                status=status if status not in {"blocked", "failed"} else status,
                result=result,
                error_code="" if status == "completed" else status,
                error_message=str(fetched.get("error") or "")[:500],
            )
            return result
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            if request_persisted:
                raise AcquisitionRecoveryRequiredError(
                    "Request outcome is durable but a later Phase A persistence boundary failed."
                ) from exc
            if dispatch_started:
                uncertainty_type = type(exc).__name__.casefold()
                store.complete_request(
                    request_id,
                    status="uncertain",
                    uncertain_external_outcome=True,
                    recovery_state="recovery_required",
                    error_code=f"uncertain_external_outcome:{uncertainty_type}",
                    error_message=(
                        "External acquisition may have occurred before persistence completed; "
                        f"exception_type={uncertainty_type}."
                    ),
                )
                raise AcquisitionUncertainOutcomeError(
                    "External acquisition outcome is uncertain; explicit recovery is required."
                ) from exc
            store.complete_request(
                request_id,
                status="blocked",
                recovery_state="not_dispatched",
                error_code="dispatch_blocked",
                error_message=str(exc)[:500],
            )
            raise AcquisitionDispatchBlockedError("Phase A dispatch was rejected before the external call.") from exc

    def _emit_stale_alert_if_needed(self, target: Mapping[str, Any]) -> None:
        last_success = str(target.get("last_success_at") or "").strip()
        if not last_success:
            return
        try:
            observed = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() / 3600
        except ValueError:
            return
        stale_limit = _as_int(self._phase_i_config("stale_catalog_alert_hours", 48), 48)
        if age_hours > stale_limit:
            self._emit(
                "acquisition_catalog_stale",
                target_id=str(target.get("target_id") or ""),
                age_hours=round(age_hours, 2),
                threshold_hours=stale_limit,
            )


__all__ = [
    "AcquisitionDispatchBlockedError",
    "AcquisitionRecoveryRequiredError",
    "AcquisitionUncertainOutcomeError",
    "PHASE_A_DEFAULT_CONFIG",
    "PhaseAAcquisitionScheduler",
]
