from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.application.contracts import BackendRegistriesProtocol, StageEngineProtocol
from backend.database.connection import transient_database_error_category
from backend.domain.models import (
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    STAGE_STATUS_COMPLETED,
    STAGE_STATUS_FAILED,
    STAGE_STATUS_SKIPPED,
    WORKER_STATUS_IDLE,
    WORKER_STATUS_RUNNING,
    WORKER_STATUS_STALE,
    WORKER_STATUS_STOPPED,
    ArtifactRecord,
    JobRecord,
    ReviewRecord,
    RunRecord,
    StageContext,
    WorkerRecord,
    WorkflowTemplate,
    WorkspaceDefinition,
    utc_plus_seconds,
    utc_now_iso,
)
from backend.domain.tracker import (
    PLACED_IN_TRACKER_AT_METADATA_KEY,
    ensure_review_placed_in_tracker_at,
    review_placed_in_tracker_at,
)
from backend.profiles.cv_upload_jobs import is_cv_upload_processing_run, process_cv_upload_run
from backend.repositories.contracts import BackendRepositories


WorkspaceValidator = Callable[..., None]
RuntimeValueResolver = Callable[[Any], Any]
TrackerDuplicateGuard = Callable[..., dict[str, str]]
TrackerReviewPredicate = Callable[[ReviewRecord], bool]
AutoApproveGeneratedReviews = Callable[..., None]
ScheduledRunEnqueuer = Callable[[], list[RunRecord]]


@dataclass(slots=True)
class RunLifecycleService:
    repositories: BackendRepositories
    registries: BackendRegistriesProtocol
    stage_engine: StageEngineProtocol
    validate_workspace: WorkspaceValidator
    validation_error_type: type[Exception]
    resolve_runtime_value: RuntimeValueResolver
    review_is_actionable_tracker_item: TrackerReviewPredicate
    find_duplicate_user_tracker_posting: TrackerDuplicateGuard
    auto_approve_generated_job_reviews: AutoApproveGeneratedReviews
    enqueue_due_scheduled_runs: ScheduledRunEnqueuer
    object_storage: Any = None

    def get_run(self, run_id: str) -> RunRecord:
        return self.repositories.run_repository.get(run_id)

    def delete_run(self, run_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        deletable_statuses = {
            RUN_STATUS_PLANNED,
            RUN_STATUS_QUEUED,
            RUN_STATUS_CANCELLED,
            RUN_STATUS_FAILED,
            RUN_STATUS_COMPLETED,
        }
        if run.status not in deletable_statuses:
            raise ValueError(
                "only planned, queued, completed, failed, or cancelled runs can be deleted",
            )

        self.repositories.job_store.clear_run(run_id)
        self.repositories.artifact_store.clear_run(run_id)

        for review in self.list_reviews(run_id=run_id, limit=100000, offset=0):
            self.repositories.review_store.delete_review(review.review_id)

        for worker in self.list_workers(limit=1000, offset=0, status=""):
            if worker.current_run_id != run_id:
                continue
            worker.current_run_id = ""
            worker.status = WORKER_STATUS_IDLE
            worker.last_heartbeat_at = utc_now_iso()
            worker.lease_expires_at = worker.last_heartbeat_at
            self.repositories.worker_store.upsert_worker(worker)

        self.repositories.run_repository.delete(run_id)

    def list_runs(self, *, limit: int = 50, offset: int = 0, status: str = "", workspace_id: str = ""):
        repository = self.repositories.run_repository
        try:
            return repository.list_runs(limit=limit, offset=offset, status=status, workspace_id=workspace_id)
        except TypeError:
            runs = repository.list_runs(
                limit=max(1, int(limit)) + max(0, int(offset)),
                status=status,
                workspace_id=workspace_id,
            )
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return runs[normalized_offset : normalized_offset + normalized_limit]

    def list_job_sets(self, run_id: str) -> dict[str, list[JobRecord]]:
        self.repositories.run_repository.get(run_id)
        return self.repositories.job_store.load_all_job_sets(run_id)

    def get_job_set(self, run_id: str, set_key: str) -> list[JobRecord]:
        self.repositories.run_repository.get(run_id)
        return self.repositories.job_store.load_job_set(run_id, set_key)

    def upsert_job_set(self, run_id: str, set_key: str, jobs: list[Mapping[str, Any] | JobRecord]) -> list[JobRecord]:
        self.repositories.run_repository.get(run_id)
        job_records = [job if isinstance(job, JobRecord) else JobRecord.from_mapping(job) for job in jobs]
        self.repositories.job_store.save_job_set(run_id, set_key, job_records)
        self.refresh_run_job_keys(run_id)
        return self.repositories.job_store.load_job_set(run_id, set_key)

    def delete_job_set(self, run_id: str, set_key: str) -> None:
        self.repositories.run_repository.get(run_id)
        self.repositories.job_store.delete_job_set(run_id, set_key)
        self.refresh_run_job_keys(run_id)

    def delete_job(self, run_id: str, job_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        if run.status in {RUN_STATUS_RUNNING, RUN_STATUS_CANCEL_REQUESTED}:
            raise ValueError("stop the run before deleting jobs")

        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            raise ValueError("job_id is required")

        removed_from_job_sets = False
        removed_reviews = False
        removed_artifacts = False
        removed_blob_references = False
        remaining_job_ids: set[str] = set()

        for set_key, jobs in self.list_job_sets(run_id).items():
            remaining_jobs = [job for job in jobs if job.job_id != normalized_job_id]
            remaining_job_ids.update(
                str(job.job_id or "").strip()
                for job in remaining_jobs
                if str(job.job_id or "").strip()
            )
            if len(remaining_jobs) == len(jobs):
                continue
            removed_from_job_sets = True
            if remaining_jobs:
                self.repositories.job_store.save_job_set(run_id, set_key, remaining_jobs)
            else:
                self.repositories.job_store.delete_job_set(run_id, set_key)

        for review in self.list_reviews(run_id=run_id, limit=100000, offset=0):
            if review.job_id != normalized_job_id:
                continue
            self.repositories.review_store.delete_review(review.review_id)
            removed_reviews = True

        for artifact in self.list_artifacts(run_id):
            should_delete_artifact = _artifact_matches_job(artifact, normalized_job_id)
            if not should_delete_artifact and not remaining_job_ids:
                should_delete_artifact = _artifact_is_generated_document_container(artifact)
            if not should_delete_artifact:
                continue
            self.repositories.artifact_store.delete_artifact(run_id, artifact.artifact_id)
            removed_artifacts = True

        for blob_key in self.repositories.job_store.list_blob_keys(run_id):
            blob_value = self.repositories.job_store.load_blob(run_id, blob_key, None)
            cleaned_blob_value, blob_changed = _remove_job_from_blob_payload(blob_value, normalized_job_id)
            if not blob_changed:
                continue
            self.repositories.job_store.save_blob(run_id, blob_key, cleaned_blob_value)
            removed_blob_references = True

        if not any(
            (
                removed_from_job_sets,
                removed_reviews,
                removed_artifacts,
                removed_blob_references,
            )
        ):
            raise KeyError(f"Job '{normalized_job_id}' not found for run '{run_id}'.")

        self.refresh_run_job_keys(run_id)

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        self.repositories.run_repository.get(run_id)
        return self.repositories.artifact_store.load_artifacts(run_id)

    def get_artifact(self, run_id: str, artifact_id: str) -> ArtifactRecord:
        self.repositories.run_repository.get(run_id)
        return self.repositories.artifact_store.get_artifact(run_id, artifact_id)

    def upsert_artifact(self, run_id: str, payload: Mapping[str, Any] | ArtifactRecord) -> ArtifactRecord:
        self.repositories.run_repository.get(run_id)
        artifact = payload if isinstance(payload, ArtifactRecord) else ArtifactRecord.from_dict(payload)
        if not artifact.artifact_id:
            raise ValueError("artifact_id is required")
        publisher = getattr(self.stage_engine, "artifact_publisher", None)
        if callable(publisher):
            artifact = list(publisher(run_id, [artifact]))[0]
        self.repositories.artifact_store.upsert_artifact(run_id, artifact)
        return self.repositories.artifact_store.get_artifact(run_id, artifact.artifact_id)

    def delete_artifact(self, run_id: str, artifact_id: str) -> None:
        self.repositories.run_repository.get(run_id)
        self.repositories.artifact_store.delete_artifact(run_id, artifact_id)

    def list_reviews(
        self,
        *,
        run_id: str = "",
        job_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewRecord]:
        repository = self.repositories.review_store
        try:
            return repository.list_reviews(run_id=run_id, job_id=job_id, limit=limit, offset=offset)
        except TypeError:
            reviews = repository.list_reviews(
                run_id=run_id,
                job_id=job_id,
                limit=max(1, int(limit)) + max(0, int(offset)),
            )
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return reviews[normalized_offset : normalized_offset + normalized_limit]

    def get_review(self, review_id: str) -> ReviewRecord:
        return self.repositories.review_store.get_review(review_id)

    def upsert_review(
        self,
        *,
        run_id: str,
        payload: Mapping[str, Any] | ReviewRecord,
        review_id: str = "",
    ) -> ReviewRecord:
        self.repositories.run_repository.get(run_id)
        review = payload if isinstance(payload, ReviewRecord) else ReviewRecord.from_dict(payload)
        if not review.job_id:
            raise ValueError("job_id is required")
        normalized_review_id = str(review_id or review.review_id or "").strip()
        existing_review = None
        if normalized_review_id:
            try:
                existing_review = self.repositories.review_store.get_review(normalized_review_id)
            except KeyError:
                existing_review = None
        if existing_review is None:
            matching_reviews = self.list_reviews(run_id=run_id, job_id=review.job_id, limit=1, offset=0)
            if matching_reviews:
                existing_review = matching_reviews[0]
                if not normalized_review_id:
                    normalized_review_id = existing_review.review_id
        previously_actionable = bool(existing_review and self.review_is_actionable_tracker_item(existing_review))
        existing_placed_in_tracker_at = (
            review_placed_in_tracker_at(existing_review, include_legacy_fallback=False)
            if existing_review
            else ""
        )
        if not normalized_review_id:
            review = ReviewRecord.create(
                run_id=run_id,
                job_id=review.job_id,
                status=review.status,
                decision=review.decision,
                reviewer=review.reviewer,
                notes=review.notes,
                job_set_key=review.job_set_key,
                metadata=review.metadata,
            )
        else:
            review.review_id = normalized_review_id
            if existing_review is not None:
                review.created_at = existing_review.created_at
                if not review.job_set_key:
                    review.job_set_key = existing_review.job_set_key
                review.metadata = {
                    **dict(existing_review.metadata or {}),
                    **dict(review.metadata or {}),
                }
        review.run_id = run_id
        review.updated_at = utc_now_iso()
        review.metadata = dict(review.metadata or {})
        review.metadata.pop(PLACED_IN_TRACKER_AT_METADATA_KEY, None)
        ensure_review_placed_in_tracker_at(
            review,
            previously_actionable=previously_actionable,
            existing_placed_in_tracker_at=existing_placed_in_tracker_at,
        )
        if self.review_is_actionable_tracker_item(review):
            duplicate = self.find_duplicate_user_tracker_posting(
                run_id=run_id,
                job_id=review.job_id,
                review_id=review.review_id,
            )
            if duplicate:
                raise ValueError(
                    "This posting URL is already tracked for this user; duplicate applications are blocked."
                )
        self.repositories.review_store.upsert_review(review)
        return self.repositories.review_store.get_review(review.review_id)

    def delete_review(self, review_id: str) -> None:
        self.repositories.review_store.delete_review(review_id)

    def list_workers(self, *, limit: int = 50, offset: int = 0, status: str = "") -> list[WorkerRecord]:
        repository = self.repositories.worker_store
        try:
            return repository.list_workers(limit=limit, offset=offset, status=status)
        except TypeError:
            workers = repository.list_workers(limit=max(1, int(limit)) + max(0, int(offset)), status=status)
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return workers[normalized_offset : normalized_offset + normalized_limit]

    def get_worker(self, worker_id: str) -> WorkerRecord:
        return self.repositories.worker_store.get_worker(worker_id)

    def heartbeat_worker(
        self,
        *,
        worker_id: str,
        status: str = WORKER_STATUS_IDLE,
        current_run_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
        metadata: Mapping[str, Any] | None = None,
    ) -> WorkerRecord:
        now = utc_now_iso()
        try:
            worker = self.repositories.worker_store.get_worker(worker_id)
        except KeyError:
            worker = WorkerRecord.create(
                worker_id=worker_id,
                status=status,
                host_name=host_name,
                process_id=process_id,
                current_run_id=current_run_id,
                lease_expires_at=utc_plus_seconds(lease_seconds),
                metadata=metadata,
            )
        worker.status = status
        worker.current_run_id = str(current_run_id or "")
        worker.host_name = str(host_name or worker.host_name)
        worker.process_id = int(process_id or worker.process_id or 0)
        worker.last_heartbeat_at = now
        worker.lease_expires_at = utc_plus_seconds(lease_seconds)
        if metadata is not None:
            worker.metadata = dict(metadata)
        self.repositories.worker_store.upsert_worker(worker)
        return self.repositories.worker_store.get_worker(worker.worker_id)

    def stop_worker(self, worker_id: str) -> WorkerRecord:
        worker = self.repositories.worker_store.get_worker(worker_id)
        worker.status = WORKER_STATUS_STOPPED
        worker.current_run_id = ""
        worker.last_heartbeat_at = utc_now_iso()
        worker.lease_expires_at = worker.last_heartbeat_at
        self.repositories.worker_store.upsert_worker(worker)
        return self.repositories.worker_store.get_worker(worker_id)

    @staticmethod
    def _enabled_workflow_stage_ids(workflow: WorkflowTemplate) -> list[str]:
        return [
            str(stage.stage_id or "").strip()
            for stage in workflow.stages
            if stage.enabled and str(stage.stage_id or "").strip()
        ]

    def _completed_from_stage_results(self, run: RunRecord) -> bool:
        if any(result.status == STAGE_STATUS_FAILED for result in run.stage_results):
            return False
        enabled_stage_ids = self._enabled_workflow_stage_ids(self.workflow_from_run_snapshot(run))
        if not enabled_stage_ids:
            return False
        results_by_stage = {result.stage_id: result.status for result in run.stage_results}
        return all(
            results_by_stage.get(stage_id) in {STAGE_STATUS_COMPLETED, STAGE_STATUS_SKIPPED}
            for stage_id in enabled_stage_ids
        )

    def _finalize_completed_stage_result_run(self, run: RunRecord, *, now: str) -> RunRecord:
        run.status = RUN_STATUS_COMPLETED
        run.final_job_set_keys = sorted(self.repositories.job_store.list_job_set_keys(run.id))
        run.current_stage_id = ""
        run.last_error = ""
        run.finished_at = run.finished_at or max(
            (
                str(result.finished_at or "")
                for result in run.stage_results
                if str(result.finished_at or "").strip()
            ),
            default=now,
        )
        run.updated_at = now
        run.metadata.pop("progress", None)
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def recover_stale_workers(self) -> list[WorkerRecord]:
        now = utc_now_iso()
        stale_workers = self.repositories.worker_store.list_expired_workers(expires_before=now)
        recovered: list[WorkerRecord] = []
        for worker in stale_workers:
            if worker.current_run_id:
                try:
                    run = self.repositories.run_repository.get(worker.current_run_id)
                except KeyError:
                    run = None
                if run is not None and run.status in {RUN_STATUS_RUNNING, RUN_STATUS_CANCEL_REQUESTED}:
                    if self._completed_from_stage_results(run):
                        self._finalize_completed_stage_result_run(run, now=now)
                    else:
                        run.status = RUN_STATUS_QUEUED
                        run.current_stage_id = ""
                        run.updated_at = now
                        run.last_error = "Recovered from expired worker lease."
                        run.metadata.pop("progress", None)
                        self.repositories.run_repository.save(run)
            worker.status = WORKER_STATUS_STALE
            worker.current_run_id = ""
            worker.last_heartbeat_at = now
            worker.lease_expires_at = now
            self.repositories.worker_store.upsert_worker(worker)
            recovered.append(worker)
        return recovered

    def fail_run_preflight(self, run: RunRecord, exc: Exception) -> RunRecord:
        now = utc_now_iso()
        metadata = dict(run.metadata or {})
        metadata["preflight_error"] = {
            "code": getattr(exc, "error_code", "run_preflight_failed"),
            "message": str(exc),
            "details": dict(getattr(exc, "details", {}) or {}),
        }
        run.metadata = metadata
        run.status = RUN_STATUS_FAILED
        run.current_stage_id = ""
        run.last_error = str(exc)
        run.finished_at = now
        run.updated_at = now
        run.metadata.pop("progress", None)
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def start_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        execute: bool = True,
        enqueue: bool = False,
        requested_by: str = "cli",
        user_id: str = "",
        max_attempts: int = 1,
    ) -> RunRecord:
        if execute and enqueue:
            raise ValueError("run cannot be both queued and synchronously executed")
        workspace = self.repositories.workspace_repository.get_workspace(workspace_id)
        self.validate_workspace(
            workspace,
            phase="run_preflight",
            error_code="run_preflight_failed",
        )
        workflow = self.repositories.workspace_repository.get_workflow_template(workspace.workflow_template_id)

        run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=workflow.id,
            run_input_overrides=run_input_overrides or {},
            requested_by=requested_by,
            user_id=user_id,
            max_attempts=max_attempts,
            metadata={
                "workspace_type": workspace.workspace_type,
                "run_mode": str((run_input_overrides or {}).get("run_mode") or "normal").strip().lower() or "normal",
                "run_kind": (
                    "test"
                    if str((run_input_overrides or {}).get("run_mode") or "").strip().lower() == "test"
                    else "standard"
                ),
            },
        )
        run.run_plan = self.stage_engine.build_run_plan(
            workspace=workspace,
            workflow=workflow,
            run_input_overrides=run_input_overrides or {},
        )
        self.validate_workspace(
            workspace,
            phase="run_preflight",
            error_code="run_preflight_failed",
            run_plan_settings=run.run_plan.resolved_run_settings if run.run_plan else {},
        )
        self.repositories.run_repository.save(run)

        if enqueue:
            return self.queue_run(run)
        if not execute:
            return self.repositories.run_repository.get(run.id)
        return self.execute_run(run, workspace=workspace, workflow=workflow, auto_retry_failed=False)

    def enqueue_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        requested_by: str = "api",
        user_id: str = "",
        max_attempts: int = 1,
    ) -> RunRecord:
        return self.start_run(
            workspace_id,
            run_input_overrides=run_input_overrides,
            execute=False,
            enqueue=True,
            requested_by=requested_by,
            user_id=user_id,
            max_attempts=max_attempts,
        )

    def claim_next_queued_run(
        self,
        *,
        worker_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
    ) -> RunRecord | None:
        if worker_id:
            self.recover_stale_workers()
        self.enqueue_due_scheduled_runs()
        run = self.repositories.run_repository.claim_next_queued()
        if run is None:
            if worker_id:
                self.heartbeat_worker(
                    worker_id=worker_id,
                    status=WORKER_STATUS_IDLE,
                    current_run_id="",
                    host_name=host_name,
                    process_id=process_id,
                    lease_seconds=lease_seconds,
                )
            return None
        if worker_id:
            self.heartbeat_worker(
                worker_id=worker_id,
                status=WORKER_STATUS_RUNNING,
                current_run_id=run.id,
                host_name=host_name,
                process_id=process_id,
                lease_seconds=lease_seconds,
            )
        return run

    def execute_claimed_run(self, run_id: str, *, auto_retry_failed: bool = True) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        if is_cv_upload_processing_run(run):
            return process_cv_upload_run(
                repositories=self.repositories,
                object_storage=self.object_storage,
                run=run,
                auto_retry_failed=auto_retry_failed,
            )
        workspace = self.workspace_from_run_snapshot(run)
        workflow = self.workflow_from_run_snapshot(run)
        try:
            self.validate_workspace(
                workspace,
                phase="run_preflight",
                error_code="run_preflight_failed",
                run_plan_settings=run.run_plan.resolved_run_settings if run.run_plan else {},
            )
        except self.validation_error_type as exc:
            return self.fail_run_preflight(run, exc)
        return self.execute_run(run, workspace=workspace, workflow=workflow, auto_retry_failed=auto_retry_failed)

    def release_worker(self, worker_id: str, *, status: str = WORKER_STATUS_IDLE) -> WorkerRecord | None:
        if not worker_id:
            return None
        try:
            worker = self.repositories.worker_store.get_worker(worker_id)
        except KeyError:
            return None
        worker.status = status
        worker.current_run_id = ""
        worker.last_heartbeat_at = utc_now_iso()
        worker.lease_expires_at = worker.last_heartbeat_at
        self.repositories.worker_store.upsert_worker(worker)
        return self.repositories.worker_store.get_worker(worker_id)

    def process_next_queued_run(
        self,
        *,
        auto_retry_failed: bool = True,
        worker_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
    ) -> RunRecord | None:
        run = self.claim_next_queued_run(
            worker_id=worker_id,
            host_name=host_name,
            process_id=process_id,
            lease_seconds=lease_seconds,
        )
        if run is None:
            return None
        try:
            return self.execute_claimed_run(run.id, auto_retry_failed=auto_retry_failed)
        finally:
            if worker_id:
                self.release_worker(worker_id)

    def cancel_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        now = utc_now_iso()
        if run.status in {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            return run
        if run.status == RUN_STATUS_RUNNING:
            run.status = RUN_STATUS_CANCEL_REQUESTED
        else:
            run.status = RUN_STATUS_CANCELLED
            run.finished_at = now
            run.current_stage_id = ""
            run.metadata.pop("progress", None)
        run.updated_at = now
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def retry_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        if run.status not in {RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            raise ValueError("only failed or cancelled runs can be retried")
        self.validate_workspace(
            self.workspace_from_run_snapshot(run),
            phase="run_preflight",
            error_code="run_preflight_failed",
            run_plan_settings=run.run_plan.resolved_run_settings if run.run_plan else {},
        )
        self.repositories.job_store.clear_run(run.id)
        self.repositories.artifact_store.clear_run(run.id)
        run.stage_results = []
        run.final_job_set_keys = []
        run.current_stage_id = ""
        run.last_error = ""
        run.started_at = ""
        run.finished_at = ""
        run.metadata.pop("progress", None)
        return self.queue_run(run)

    def resume_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        if run.status not in {RUN_STATUS_PLANNED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            raise ValueError("only planned, failed, or cancelled runs can be resumed")
        self.validate_workspace(
            self.workspace_from_run_snapshot(run),
            phase="run_preflight",
            error_code="run_preflight_failed",
            run_plan_settings=run.run_plan.resolved_run_settings if run.run_plan else {},
        )
        self.trim_to_resumable_prefix(run)
        run.final_job_set_keys = sorted(self.repositories.job_store.list_job_set_keys(run.id))
        run.current_stage_id = ""
        run.last_error = ""
        run.started_at = ""
        run.finished_at = ""
        run.metadata.pop("progress", None)
        return self.queue_run(run)

    def execute_run(
        self,
        run: RunRecord,
        *,
        workspace: WorkspaceDefinition,
        workflow: WorkflowTemplate,
        auto_retry_failed: bool,
    ) -> RunRecord:
        logger = logging.getLogger(f"backend.run.{run.id}")
        raw_run_settings = dict(run.run_plan.resolved_run_settings if run.run_plan else {})
        resolved_run_settings = self.resolve_runtime_value(raw_run_settings)
        context = StageContext(
            workspace=workspace,
            workflow=workflow,
            run=run,
            repositories=self.repositories,
            registries=self.registries,
            logger=logger,
            data={
                "run_settings": raw_run_settings,
                "resolved_run_settings": resolved_run_settings,
                "secret_resolver": self.resolve_runtime_value,
            },
        )
        try:
            self.stage_engine.execute(context)
        except Exception as exc:
            if transient_database_error_category(exc) is not None:
                run = self.repositories.run_repository.get(run.id)
                if self._completed_from_stage_results(run):
                    return self._finalize_completed_stage_result_run(run, now=utc_now_iso())
                if auto_retry_failed:
                    self.trim_to_resumable_prefix(run)
                    return self.queue_run(run)
                raise
            run = self.repositories.run_repository.get(run.id)
            if auto_retry_failed and run.status == RUN_STATUS_FAILED and run.attempt_count < run.max_attempts:
                self.trim_to_resumable_prefix(run)
                self.queue_run(run)
            return self.repositories.run_repository.get(run.id)
        try:
            self.auto_approve_generated_job_reviews(run_id=run.id, workflow=workflow)
        except Exception:
            logger.exception("Unable to auto-approve generated jobs for run %s", run.id)
        return self.repositories.run_repository.get(run.id)

    def queue_run(self, run: RunRecord) -> RunRecord:
        now = utc_now_iso()
        run.status = RUN_STATUS_QUEUED
        run.queued_at = now
        run.current_stage_id = ""
        run.started_at = ""
        run.finished_at = ""
        run.updated_at = now
        run.metadata.pop("progress", None)
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def trim_to_resumable_prefix(self, run: RunRecord) -> None:
        kept_results = []
        for result in run.stage_results:
            if result.status in {"completed", "skipped"}:
                kept_results.append(result)
                continue
            break
        run.stage_results = kept_results

    def refresh_run_job_keys(self, run_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        run.final_job_set_keys = sorted(self.repositories.job_store.list_job_set_keys(run.id))
        run.updated_at = utc_now_iso()
        self.repositories.run_repository.save(run)

    def workflow_from_run_snapshot(self, run: RunRecord) -> WorkflowTemplate:
        if run.run_plan and run.run_plan.workflow_snapshot:
            return WorkflowTemplate.from_dict(run.run_plan.workflow_snapshot)
        return self.repositories.workspace_repository.get_workflow_template(run.workflow_template_id)

    def workspace_from_run_snapshot(self, run: RunRecord) -> WorkspaceDefinition:
        if run.run_plan and run.run_plan.workspace_snapshot:
            return WorkspaceDefinition.from_dict(run.run_plan.workspace_snapshot)
        return self.repositories.workspace_repository.get_workspace(run.workspace_id)


def _artifact_matches_job(artifact: ArtifactRecord, job_id: str) -> bool:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return False
    if str((artifact.metadata or {}).get("job_id") or "").strip() == normalized_job_id:
        return True
    lowered_job_id = normalized_job_id.lower()
    candidate_text = " ".join(
        value
        for value in (
            str(artifact.artifact_id or "").strip(),
            str(artifact.path or "").strip(),
            Path(str(artifact.path or "")).name if str(artifact.path or "").strip() else "",
        )
        if value
    ).lower()
    return bool(lowered_job_id and lowered_job_id in candidate_text)


def _artifact_is_generated_document_container(artifact: ArtifactRecord) -> bool:
    return str(artifact.artifact_type or "").strip().lower() in {
        "stage5_docs_dir",
        "documents_json",
        "documents_xlsx",
    }


def _remove_job_from_blob_payload(value: Any, job_id: str) -> tuple[Any, bool]:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return value, False
    if isinstance(value, list):
        next_items = []
        changed = False
        for item in value:
            if isinstance(item, dict) and str(item.get("job_id") or "").strip() == normalized_job_id:
                changed = True
                continue
            cleaned_item, item_changed = _remove_job_from_blob_payload(item, normalized_job_id)
            next_items.append(cleaned_item)
            changed = changed or item_changed
        return next_items, changed
    if isinstance(value, dict):
        next_value = {}
        changed = False
        for key, item in value.items():
            cleaned_item, item_changed = _remove_job_from_blob_payload(item, normalized_job_id)
            next_value[key] = cleaned_item
            changed = changed or item_changed
        return next_value, changed
    return value, False
