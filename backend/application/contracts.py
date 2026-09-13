from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from backend.domain.models import RunPlan, StageContext, WorkflowTemplate, WorkspaceDefinition


class RegistryProtocol(Protocol):
    def get(self, key: str) -> Any: ...

    def contains(self, key: str) -> bool: ...

    def list_items(self) -> list[tuple[str, Any]]: ...


class BackendRegistriesProtocol(Protocol):
    stage_registry: RegistryProtocol
    connector_registry: RegistryProtocol
    generation_registry: RegistryProtocol
    renderer_registry: RegistryProtocol


class StageEngineProtocol(Protocol):
    event_emitter: Callable[..., None] | None

    def build_run_plan(
        self,
        *,
        workspace: WorkspaceDefinition,
        workflow: WorkflowTemplate,
        run_input_overrides: Mapping[str, Any] | None = None,
    ) -> RunPlan: ...

    def execute(self, context: StageContext) -> Any: ...
