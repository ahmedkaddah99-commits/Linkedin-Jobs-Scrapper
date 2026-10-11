from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from backend.database.connection import transient_database_error_category
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
TEST_RUN_OUTPUT_STAGE_TYPES = {
    *DOCUMENT_GENERATION_STAGE_TYPES,
    "profiles.generate.reusable",
    "applications.package.export",
    "legacy.blue_collar.stage4",
    "legacy.blue_collar.stage5",
}
TEST_RUN_MODE = "test"
TEST_RUN_JOB_LIMIT = 1


class StageEngine:
    def __init__(
        self,
        *,
        stage_registry,
        run_repository,
        job_store,
        artifact_store,
        event_emitter=None,
        artifact_publisher=None,
    ):
        self.stage_registry = stage_registry
        self.run_repository = run_repository
        self.job_store = job_store
        self.artifact_store = artifact_store
        self.event_emitter = event_emitter
        self.artifact_publisher = artifact_publisher

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
        total_stage_count = len(context.workflow.stages)
        completed_stage_ids = {
            result.stage_id
            for result in run.stage_results
            if result.status in {STAGE_STATUS_COMPLETED, STAGE_STATUS_SKIPPED}
        }

        for stage_index, definition in enumerate(context.workflow.stages, start=1):
            if definition.stage_id in completed_stage_ids:
                continue
            if self._cancel_requested(run.id):
                self._cancel_run(context, definition=definition)
                return context.run

            run.current_stage_id = definition.stage_id
            run.updated_at = utc_now_iso()
            self.run_repository.save(run)
            context.update_run_progress(
                stage_id=definition.stage_id,
                stage_type=definition.stage_type,
                stage_name=definition.name,
                message=f"Running {definition.name or definition.stage_id}",
                counters={
                    "stage_index": stage_index,
                    "total_stages": total_stage_count,
                    "completed_stages": len(completed_stage_ids),
                },
                status="running",
                extra={"stage_description": str(definition.description or "")},
            )

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
                self._limit_test_run_generation_inputs(context, definition)
                outcome = stage.execute(context, definition)
                self._limit_test_run_output(context, definition, outcome)
            except Exception as exc:
                if self._cancel_requested(run.id):
                    self._cancel_run(context, definition=definition)
                    return context.run
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
                context.update_run_progress(
                    stage_id=definition.stage_id,
                    stage_type=definition.stage_type,
                    stage_name=definition.name,
                    message=f"{definition.name or definition.stage_id} failed",
                    counters={},
                    recent_failures=[{"stage": definition.stage_id, "error": str(exc)}],
                    status="failed",
                    extra={"stage_description": str(definition.description or "")},
                    save=False,
                )
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
            try:
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
                    if callable(self.artifact_publisher):
                        outcome.artifacts = list(self.artifact_publisher(run.id, outcome.artifacts))
                    context.artifacts.extend(outcome.artifacts)
                    self.artifact_store.save_artifacts(run.id, context.artifacts)

                if definition.stage_type in DOCUMENT_GENERATION_STAGE_TYPES:
                    self._validate_document_generation_output(
                        context=context,
                        definition=definition,
                        outcome=outcome,
                    )
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
                completed_stage_ids.add(definition.stage_id)
            except Exception as exc:
                if transient_database_error_category(exc) is not None:
                    raise
                failed_artifact_ids = [
                    artifact.artifact_id
                    for artifact in list(getattr(outcome, "artifacts", []) or [])
                ]
                self._append_stage_result(
                    context=context,
                    definition=definition,
                    status=STAGE_STATUS_FAILED,
                    started_at=started_at,
                    finished_at=utc_now_iso(),
                    metrics=dict(getattr(outcome, "metrics", {}) or {}),
                    output_keys=output_keys,
                    artifact_ids=failed_artifact_ids,
                    error=str(exc),
                )
                run.status = RUN_STATUS_FAILED
                run.finished_at = utc_now_iso()
                run.current_stage_id = definition.stage_id
                run.last_error = str(exc)
                run.updated_at = utc_now_iso()
                context.update_run_progress(
                    stage_id=definition.stage_id,
                    stage_type=definition.stage_type,
                    stage_name=definition.name,
                    message=f"{definition.name or definition.stage_id} failed",
                    counters={},
                    recent_failures=[{"stage": definition.stage_id, "error": str(exc)}],
                    status="failed",
                    extra={"stage_description": str(definition.description or "")},
                    save=False,
                )
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

        run.status = RUN_STATUS_COMPLETED
        run.final_job_set_keys = sorted(context.job_sets.keys())
        run.current_stage_id = ""
        run.last_error = ""
        run.finished_at = utc_now_iso()
        run.updated_at = utc_now_iso()
        context.clear_run_progress(save=False)
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

    def _limit_test_run_generation_inputs(self, context: StageContext, definition: StageDefinition) -> None:
        if not self._is_test_run(context) or definition.stage_type not in TEST_RUN_OUTPUT_STAGE_TYPES:
            return
        for key in definition.input_keys:
            jobs = context.get_job_set(key)
            if len(jobs) <= TEST_RUN_JOB_LIMIT:
                continue
            selected_jobs = jobs[:TEST_RUN_JOB_LIMIT]
            context.set_job_set(key, selected_jobs)
            self.job_store.save_job_set(context.run.id, key, selected_jobs)

    def _limit_test_run_output(
        self,
        context: StageContext,
        definition: StageDefinition,
        outcome: StageOutcome,
    ) -> None:
        if not self._is_test_run(context) or definition.stage_type not in TEST_RUN_OUTPUT_STAGE_TYPES:
            return
        limited_job_sets: dict[str, list[JobRecord | Mapping[str, Any]]] = {}
        for key, jobs in outcome.job_sets.items():
            limited_job_sets[key] = list(jobs)[:TEST_RUN_JOB_LIMIT]
        outcome.job_sets = limited_job_sets
        outcome.metrics = {
            **dict(outcome.metrics),
            "test_run": True,
            "test_run_job_limit": TEST_RUN_JOB_LIMIT,
        }

    @staticmethod
    def _is_test_run(context: StageContext) -> bool:
        settings = dict(context.data.get("resolved_run_settings") or {})
        return str(settings.get("run_mode") or "").strip().lower() == TEST_RUN_MODE

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
        context.clear_run_progress(save=False)
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

    def _validate_document_generation_output(
        self,
        *,
        context: StageContext,
        definition: StageDefinition,
        outcome: StageOutcome,
    ) -> None:
        output_key = str(definition.output_key or "").strip()
        generated_jobs = list(outcome.job_sets.get(output_key) or []) if output_key else []
        if not generated_jobs and outcome.job_sets:
            generated_jobs = [
                job
                for jobs in outcome.job_sets.values()
                for job in jobs
            ]

        input_jobs = [
            job
            for key in definition.input_keys
            for job in context.get_job_set(key)
        ]
        expected_job_count = len(input_jobs)
        generated_job_count = len(generated_jobs)
        usable_job_count = sum(
            1
            for job in generated_jobs
            if self._document_job_has_required_output(job, outcome.artifacts)
        )

        outcome.metrics = {
            **dict(outcome.metrics or {}),
            "expected_document_jobs": expected_job_count,
            "generated_job_records": generated_job_count,
            "usable_document_jobs": usable_job_count,
            "artifact_count": len(outcome.artifacts),
        }

        if expected_job_count > 0 and usable_job_count <= 0:
            raise RuntimeError(
                "Document generation produced no usable documents "
                f"for {expected_job_count} selected job(s)."
            )

    @staticmethod
    def _document_job_has_required_output(
        job: JobRecord | Mapping[str, Any],
        artifacts: list[ArtifactRecord],
    ) -> bool:
        job_payload = job.to_dict() if isinstance(job, JobRecord) else dict(job or {})
        if str(job_payload.get("doc_generation_error") or "").strip():
            return False
        if str(
            job_payload.get("cv_docx")
            or job_payload.get("tailored_cv_docx")
            or job_payload.get("applied_cv")
            or ""
        ).strip():
            return True

        job_id = str(job_payload.get("job_id") or "").strip()
        if not job_id:
            return False
        for artifact in artifacts:
            artifact_type = str(artifact.artifact_type or "").strip().lower()
            if artifact_type not in {"cv_docx", "docx", "tailored_cv_docx", "applied_cv"}:
                continue
            if str((artifact.metadata or {}).get("job_id") or "").strip() == job_id:
                return True
        return False

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
