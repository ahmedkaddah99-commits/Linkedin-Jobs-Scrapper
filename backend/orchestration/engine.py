from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from backend.domain.models import (
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
    STAGE_STATUS_CANCELLED,
    STAGE_STATUS_COMPLETED,
    STAGE_STATUS_FAILED,
    STAGE_STATUS_SKIPPED,
    ArtifactRecord,
    JobRecord,
    RunPlan,
    StageContext,
    StageDefinition,
    StageResult,
    utc_now_iso,
)


@dataclass(slots=True)
class StageOutcome:
    job_sets: dict[str, list[JobRecord | Mapping[str, Any]]] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class BaseStage(ABC):
    @abstractmethod
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        raise NotImplementedError

    @abstractmethod
    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        raise NotImplementedError

    def outputs(self, definition: StageDefinition) -> list[str]:
        return [definition.output_key] if definition.output_key else []

    def validation_schema(self) -> dict[str, Any]:
        return {}


DOCUMENT_GENERATION_STAGE_TYPES = {
    "applications.generate.documents",
    "legacy.white_collar.docs",
}


class StageEngine:
    def __init__(self, *, stage_registry, run_repository, job_store, artifact_store, event_emitter=None):
        self.stage_registry = stage_registry
        self.run_repository = run_repository
        self.job_store = job_store
        self.artifact_store = artifact_store
        self.event_emitter = event_emitter

    def build_run_plan(
        self,
        *,
        workspace,
        workflow,
        run_input_overrides: Mapping[str, Any] | None = None,
    ) -> RunPlan:
        resolved_settings = dict(workflow.default_run_settings)
        resolved_settings.update(dict(workspace.settings))
        resolved_settings.update(dict(run_input_overrides or {}))
        return RunPlan(
            workflow_template_id=workflow.id,
            workspace_snapshot=workspace.to_dict(),
            workflow_snapshot=workflow.to_dict(),
            resolved_run_settings=resolved_settings,
        )

    def execute(self, context: StageContext):
        run = context.run
        self._restore_context(context)
        self._mark_run_running(run)
        completed_stage_ids = {
            result.stage_id
            for result in run.stage_results
            if result.status in {STAGE_STATUS_COMPLETED, STAGE_STATUS_SKIPPED}
        }

        for definition in context.workflow.stages:
            if definition.stage_id in completed_stage_ids:
                continue
            if self._cancel_requested(run.id):
                self._cancel_run(context, definition=definition)
                return context.run

            run.current_stage_id = definition.stage_id
            run.updated_at = utc_now_iso()
            self.run_repository.save(run)

            if not definition.enabled:
                self._append_stage_result(
                    context=context,
                    definition=definition,
                    status=STAGE_STATUS_SKIPPED,
                    started_at=utc_now_iso(),
                    finished_at=utc_now_iso(),
                    metrics={"reason": "disabled_in_workflow"},
                )
                continue

            started_at = utc_now_iso()

            try:
                stage = self.stage_registry.get(definition.stage_type)
                if not stage.can_run(context, definition):
                    self._append_stage_result(
                        context=context,
                        definition=definition,
                        status=STAGE_STATUS_SKIPPED,
                        started_at=started_at,
                        finished_at=utc_now_iso(),
                        metrics={"reason": "can_run_returned_false"},
                    )
                    continue
                outcome = stage.execute(context, definition)
            except Exception as exc:
                self._append_stage_result(
                    context=context,
                    definition=definition,
                    status=STAGE_STATUS_FAILED,
                    started_at=started_at,
                    finished_at=utc_now_iso(),
                    error=str(exc),
                )
                run.status = RUN_STATUS_FAILED
                run.finished_at = utc_now_iso()
                run.current_stage_id = definition.stage_id
                run.last_error = str(exc)
                run.updated_at = utc_now_iso()
                self.run_repository.save(run)
                self._emit_event(
                    "automation_step_failed",
                    user_id=run.normalized_user_id,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    job_id="",
                    source="runtime",
                    stage_type=definition.stage_type,
                    error=str(exc),
                    attempt_count=run.attempt_count,
                )
                self._emit_event(
                    "run_failed",
                    user_id=run.normalized_user_id,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    source="runtime",
                    status=run.status,
                    duration_seconds=self._duration_seconds(run.started_at, run.finished_at),
                    stage_count=len(run.stage_results),
                    last_error=run.last_error,
                )
                raise

            output_keys: list[str] = []
            for key, jobs in outcome.job_sets.items():
                context.set_job_set(key, jobs)
                self.job_store.save_job_set(run.id, key, context.get_job_set(key))
                output_keys.append(key)

            if outcome.data:
                context.data.update(outcome.data)
                for key, value in outcome.data.items():
                    self.job_store.save_blob(run.id, key, value)
                    output_keys.append(key)

            if outcome.artifacts:
                context.artifacts.extend(outcome.artifacts)
                self.artifact_store.save_artifacts(run.id, context.artifacts)

            if definition.stage_type in DOCUMENT_GENERATION_STAGE_TYPES:
                self._emit_document_generation_events(
                    run=run,
                    definition=definition,
                    outcome=outcome,
                )

            self._append_stage_result(
                context=context,
                definition=definition,
                status=STAGE_STATUS_COMPLETED,
                started_at=started_at,
                finished_at=utc_now_iso(),
                metrics=outcome.metrics,
                output_keys=output_keys,
                artifact_ids=[artifact.artifact_id for artifact in outcome.artifacts],
            )

        run.status = RUN_STATUS_COMPLETED
        run.final_job_set_keys = sorted(context.job_sets.keys())
        run.current_stage_id = ""
        run.last_error = ""
        run.finished_at = utc_now_iso()
        run.updated_at = utc_now_iso()
        self.run_repository.save(run)
        self._emit_event(
            "run_completed",
            user_id=run.normalized_user_id,
            workspace_id=run.workspace_id,
            run_id=run.id,
            source="runtime",
            status=run.status,
            duration_seconds=self._duration_seconds(run.started_at, run.finished_at),
            stage_count=len(run.stage_results),
            last_error=run.last_error,
        )
        return run

    def _mark_run_running(self, run) -> None:
        if run.status != RUN_STATUS_RUNNING:
            run.status = RUN_STATUS_RUNNING
            run.attempt_count += 1
            run.started_at = utc_now_iso()
        run.last_error = ""
        run.updated_at = utc_now_iso()
        self.run_repository.save(run)

    def _restore_context(self, context: StageContext) -> None:
        persisted_job_sets = self.job_store.load_all_job_sets(context.run.id)
        if persisted_job_sets:
            context.job_sets.update(persisted_job_sets)
        persisted_blobs = self.job_store.load_all_blobs(context.run.id)
        if persisted_blobs:
            existing_data = dict(context.data)
            context.data.update(persisted_blobs)
            context.data.update(existing_data)
        context.artifacts = self.artifact_store.load_artifacts(context.run.id)

    def _cancel_requested(self, run_id: str) -> bool:
        latest_run = self.run_repository.get(run_id)
        return latest_run.status in {RUN_STATUS_CANCEL_REQUESTED, RUN_STATUS_CANCELLED}

    def _cancel_run(self, context: StageContext, *, definition: StageDefinition | None) -> None:
        if definition is not None:
            self._append_stage_result(
                context=context,
                definition=definition,
                status=STAGE_STATUS_CANCELLED,
                started_at=utc_now_iso(),
                finished_at=utc_now_iso(),
                metrics={"reason": "cancel_requested"},
            )
        context.run.status = RUN_STATUS_CANCELLED
        context.run.current_stage_id = ""
        context.run.finished_at = utc_now_iso()
        context.run.updated_at = utc_now_iso()
        self.run_repository.save(context.run)

    def _append_stage_result(
        self,
        *,
        context: StageContext,
        definition: StageDefinition,
        status: str,
        started_at: str,
        finished_at: str,
        metrics: Mapping[str, Any] | None = None,
        error: str = "",
        output_keys: list[str] | None = None,
        artifact_ids: list[str] | None = None,
    ) -> None:
        result = StageResult(
            stage_id=definition.stage_id,
            stage_type=definition.stage_type,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            metrics=dict(metrics or {}),
            error=error,
            output_keys=list(output_keys or []),
            artifact_ids=list(artifact_ids or []),
        )
        context.run.stage_results.append(result)
        context.run.updated_at = utc_now_iso()
        self.run_repository.save(context.run)

    def _emit_event(self, event_name: str, **payload) -> None:
        if callable(self.event_emitter):
            self.event_emitter(event_name, **payload)

    def _emit_document_generation_events(self, *, run, definition: StageDefinition, outcome: StageOutcome) -> None:
        generated_jobs = int(outcome.metrics.get("generated_jobs") or 0)
        user_id = run.normalized_user_id
        for jobs in outcome.job_sets.values():
            for job in jobs:
                job_payload = job.to_dict() if isinstance(job, JobRecord) else dict(job or {})
                self._emit_event(
                    "cv_generation_completed",
                    user_id=user_id,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    job_id=str(job_payload.get("job_id") or ""),
                    source=definition.stage_type,
                    generated_jobs=generated_jobs,
                    ats_best_score=job_payload.get("ats_best_score"),
                    ats_stop_reason=job_payload.get("ats_stop_reason"),
                    doc_generation_errors=job_payload.get("doc_generation_error"),
                )

    @staticmethod
    def _duration_seconds(started_at: str, finished_at: str) -> float:
        started = str(started_at or "").strip()
        finished = str(finished_at or "").strip()
        if not started or not finished:
            return 0.0
        try:
            delta = datetime.fromisoformat(finished) - datetime.fromisoformat(started)
        except ValueError:
            return 0.0
        return max(delta.total_seconds(), 0.0)
