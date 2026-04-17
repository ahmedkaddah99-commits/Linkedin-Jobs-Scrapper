from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.capabilities.blue_collar.acquisition import build_stage1_args as build_blue_stage1_args
from backend.capabilities.blue_collar.acquisition import run_stage1_pipeline as run_blue_stage1_pipeline
from backend.capabilities.blue_collar.classification import build_stage3_args as build_blue_stage3_args
from backend.capabilities.blue_collar.classification import run_stage3_pipeline as run_blue_stage3_pipeline
from backend.capabilities.blue_collar.filtering import build_stage2_args as build_blue_stage2_args
from backend.capabilities.blue_collar.filtering import run_stage2_pipeline as run_blue_stage2_pipeline
from backend.capabilities.blue_collar.packaging import build_stage5_args as build_blue_stage5_args
from backend.capabilities.blue_collar.packaging import run_stage5_pipeline as run_blue_stage5_pipeline
from backend.capabilities.blue_collar.role_cvs import build_stage4_args as build_blue_stage4_args
from backend.capabilities.blue_collar.role_cvs import run_stage4_pipeline as run_blue_stage4_pipeline
from backend.capabilities.blue_collar.support import load_blue_collar_config
from backend.capabilities.white_collar.acquisition import run_stage1_pipeline as run_white_stage1_pipeline
from backend.capabilities.white_collar.documents import run_stage4_pipeline as run_white_stage4_pipeline
from backend.domain.models import ArtifactRecord, JobRecord, StageContext, StageDefinition
from backend.orchestration.engine import BaseStage, StageOutcome


def _to_job_records(records: list[dict[str, Any]]) -> list[JobRecord]:
    return [JobRecord.from_mapping(record) for record in records]


def _json_artifact(run_id: str, stage_id: str, artifact_type: str, path: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=f"{run_id}_{stage_id}_{artifact_type}",
        artifact_type=artifact_type,
        path=path,
    )
def _namespace_from_defaults(defaults: dict[str, Any], overrides: dict[str, Any]) -> SimpleNamespace:
    merged = dict(defaults)
    merged.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**merged)


def _resolved_settings(context: StageContext, definition: StageDefinition) -> dict[str, Any]:
    settings = dict(context.data.get("resolved_run_settings") or {})
    settings.update(definition.config or {})
    resolver = context.data.get("secret_resolver")
    if callable(resolver):
        return dict(resolver(settings))
    return settings


def _build_root_cli_args(context: StageContext, definition: StageDefinition):
    from job_seeker_config import load_job_seeker_config, load_project_dotenv
    from pipeline_runner import build_main_defaults

    load_project_dotenv()
    config = load_job_seeker_config()
    defaults = build_main_defaults(config)
    cli_args = _namespace_from_defaults(defaults, _resolved_settings(context, definition))
    return config, cli_args


class LinkedInAcquireStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return True

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from pipeline_runner import build_stage1_args

        connector_id = str(definition.config.get("connector_id") or "")
        if connector_id:
            context.registries.connector_registry.get(connector_id)

        config, cli_args = _build_root_cli_args(context, definition)
        stage_args = build_stage1_args(config, cli_args)
        jobs = run_white_stage1_pipeline(stage_args)
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            metrics={"jobs_found": len(jobs)},
            artifacts=[_json_artifact(context.run.id, definition.stage_id, "stage1_output", str(stage_args.output))],
        )


class ManualUrlIngestionStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return True

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from pipeline_runner import run_manual_pipeline

        connector_id = str(definition.config.get("connector_id") or "")
        if connector_id:
            context.registries.connector_registry.get(connector_id)

        _, cli_args = _build_root_cli_args(context, definition)
        jobs, failures = run_manual_pipeline(cli_args)
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            data={"manual_url_failures": failures},
            metrics={"jobs_ingested": len(jobs), "failures": len(failures)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "manual_jobs", str(cli_args.manual_output_json)),
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "manual_failures",
                    str(cli_args.manual_failures_json),
                ),
            ],
        )


class WhiteCollarLocalFilterStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from pipeline_runner import run_stage2_pipeline

        _, cli_args = _build_root_cli_args(context, definition)
        input_jobs = context.get_job_dicts(definition.input_keys[0])
        approved, rejected = run_stage2_pipeline(input_jobs, cli_args)
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(approved)},
            data={f"{definition.stage_id}_rejected": rejected},
            metrics={"approved": len(approved), "rejected": len(rejected)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "approved", str(cli_args.stage2_output)),
                _json_artifact(context.run.id, definition.stage_id, "rejected", str(cli_args.stage2_rejected_output)),
            ],
        )


class WhiteCollarRankStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from pipeline_runner import run_stage3_pipeline

        _, cli_args = _build_root_cli_args(context, definition)
        input_jobs = context.get_job_dicts(definition.input_keys[0])
        approved, rejected = run_stage3_pipeline(input_jobs, cli_args)
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(approved)},
            data={f"{definition.stage_id}_rejected": rejected},
            metrics={"approved": len(approved), "rejected": len(rejected)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "approved", str(cli_args.stage3_output)),
                _json_artifact(context.run.id, definition.stage_id, "rejected", str(cli_args.stage3_rejected_output)),
            ],
        )


class MergeJobSetsStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return any(context.get_job_set(key) for key in definition.input_keys)

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from job_dedupe import dedupe_job_records, load_existing_tracker_identity_keys

        _, cli_args = _build_root_cli_args(context, definition)
        merged_input: list[dict[str, Any]] = []
        for key in definition.input_keys:
            merged_input.extend(context.get_job_dicts(key))

        merged_jobs, dropped_duplicates = dedupe_job_records(merged_input, logger=context.logger)
        if bool(definition.config.get("dedupe_against_tracker", True)):
            existing_keys = load_existing_tracker_identity_keys(str(cli_args.output_xlsx))
            merged_jobs, dropped_against_tracker = dedupe_job_records(
                merged_jobs,
                existing_keys=existing_keys,
                logger=context.logger,
            )
            dropped_duplicates.extend(dropped_against_tracker)

        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(merged_jobs)},
            data={f"{definition.stage_id}_dropped_duplicates": dropped_duplicates},
            metrics={"merged_jobs": len(merged_jobs), "dropped_duplicates": len(dropped_duplicates)},
        )


class WhiteCollarDocsStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from pipeline_runner import build_stage4_args

        generation_id = str(definition.config.get("generation_id") or "")
        renderer_id = str(definition.config.get("renderer_id") or "")
        if generation_id:
            context.registries.generation_registry.get(generation_id)
        if renderer_id:
            context.registries.renderer_registry.get(renderer_id)

        config, cli_args = _build_root_cli_args(context, definition)
        stage4_args = build_stage4_args(cli_args)
        jobs = context.get_job_dicts(definition.input_keys[0])
        if not jobs:
            Path(stage4_args.output_json).write_text("[]", encoding="utf-8")
            return StageOutcome(job_sets={definition.output_key: []}, metrics={"generated_jobs": 0})

        Path(stage4_args.input).write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
        records = run_white_stage4_pipeline(stage4_args, config=config, jobs=jobs)
        artifacts = [
            _json_artifact(context.run.id, definition.stage_id, "documents_json", str(stage4_args.output_json)),
            _json_artifact(context.run.id, definition.stage_id, "documents_xlsx", str(stage4_args.output_xlsx)),
            _json_artifact(context.run.id, definition.stage_id, "docs_dir", str(stage4_args.docs_dir)),
        ]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(records)},
            metrics={"generated_jobs": len(records)},
            artifacts=artifacts,
        )


class BlueCollarStage1(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        connector_id = str(definition.config.get("connector_id") or "")
        if connector_id:
            context.registries.connector_registry.get(connector_id)
        return True

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_blue_collar_config()
        args = build_blue_stage1_args(config, overrides=_resolved_settings(context, definition))
        result = run_blue_stage1_pipeline(args, config=config)
        jobs = result["jobs"]
        output_path = result["output_path"]
        source_log_path = result["source_log_path"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            metrics={"jobs_found": len(jobs)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage1_output", str(output_path)),
                _json_artifact(context.run.id, definition.stage_id, "stage1_source_log", str(source_log_path)),
            ],
        )


class BlueCollarStage2(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_blue_collar_config()
        args = build_blue_stage2_args(config, overrides=_resolved_settings(context, definition))
        result = run_blue_stage2_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
        )
        jobs = result["approved_jobs"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            metrics={"approved": len(jobs)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage2_output", result["output_path"]),
                _json_artifact(context.run.id, definition.stage_id, "stage2_rejected", result["rejected_path"]),
            ],
        )


class BlueCollarStage3(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_blue_collar_config()
        args = build_blue_stage3_args(config, overrides=_resolved_settings(context, definition))
        result = run_blue_stage3_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
        )
        jobs = result["classified_jobs"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            metrics={"classified_jobs": len(jobs)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage3_output", result["output_path"]),
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "stage3_clusters",
                    result["clusters_output_path"],
                ),
            ],
        )


class BlueCollarStage4(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        generation_id = str(definition.config.get("generation_id") or "")
        if generation_id:
            context.registries.generation_registry.get(generation_id)
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_blue_collar_config()
        args = build_blue_stage4_args(config, overrides=_resolved_settings(context, definition))
        result = run_blue_stage4_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
        )
        payload = result["role_cv_index"]
        role_cvs = result["role_cv_records"]
        return StageOutcome(
            data={definition.output_key: payload},
            metrics={"role_cvs": len(role_cvs or [])},
            artifacts=[
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "stage4_role_cvs",
                    result["role_cv_index_path"],
                ),
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "stage4_role_cv_dir",
                    result["role_cv_output_dir"],
                ),
            ],
        )


class BlueCollarStage5(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        renderer_id = str(definition.config.get("renderer_id") or "")
        if renderer_id:
            context.registries.renderer_registry.get(renderer_id)
        has_jobs = bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))
        has_role_cvs = bool(context.data.get(definition.input_keys[1])) if len(definition.input_keys) > 1 else True
        return has_jobs and has_role_cvs

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_blue_collar_config()
        args = build_blue_stage5_args(config, overrides=_resolved_settings(context, definition))
        role_index_payload = context.data.get(definition.input_keys[1]) if len(definition.input_keys) > 1 else None
        result = run_blue_stage5_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
            role_index_payload=role_index_payload,
        )
        records = result["records"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(records)},
            metrics={"packaged_jobs": len(records)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage5_output", result["output_json"]),
                _json_artifact(context.run.id, definition.stage_id, "stage5_xlsx", result["output_xlsx"]),
                _json_artifact(context.run.id, definition.stage_id, "stage5_docs_dir", result["docs_root"]),
            ],
        )


def register_legacy_stage_adapters(stage_registry) -> None:
    stage_registry.register("legacy.linkedin.acquire", LinkedInAcquireStage())
    stage_registry.register("legacy.manual_url.ingest", ManualUrlIngestionStage())
    stage_registry.register("legacy.white_collar.local_filter", WhiteCollarLocalFilterStage())
    stage_registry.register("legacy.white_collar.rank", WhiteCollarRankStage())
    stage_registry.register("legacy.jobs.merge", MergeJobSetsStage())
    stage_registry.register("legacy.white_collar.docs", WhiteCollarDocsStage())
    stage_registry.register("legacy.blue_collar.stage1", BlueCollarStage1())
    stage_registry.register("legacy.blue_collar.stage2", BlueCollarStage2())
    stage_registry.register("legacy.blue_collar.stage3", BlueCollarStage3())
    stage_registry.register("legacy.blue_collar.stage4", BlueCollarStage4())
    stage_registry.register("legacy.blue_collar.stage5", BlueCollarStage5())
