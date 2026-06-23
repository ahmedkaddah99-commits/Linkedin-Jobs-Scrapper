from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from uuid import uuid4

from backend.application.contracts import BackendRegistriesProtocol
from backend.domain.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_REVIEWER,
    ROLE_VIEWER,
    SECRET_PROVIDER_ENV,
    SECRET_PROVIDER_STORED,
    ApiTokenRecord,
    RunRecord,
    SecretRecord,
    UserRecord,
    WorkflowTemplate,
    WorkspaceDefinition,
    utc_now_iso,
)
from backend.orchestration import workspace_builder_catalog
from backend.repositories.contracts import BackendRepositories
from backend.security import issue_api_token, resolve_secret_references, token_has_scope, token_is_expired, verify_token_value


WorkspaceValidator = Callable[..., None]
ALLOWED_USER_ROLES = {ROLE_ADMIN, ROLE_EDITOR, ROLE_REVIEWER, ROLE_VIEWER}


@dataclass(slots=True)
class WorkspaceCatalogService:
    repositories: BackendRepositories
    registries: BackendRegistriesProtocol
    validate_workspace: WorkspaceValidator

    def list_workspaces(self) -> list[WorkspaceDefinition]:
        return self.repositories.workspace_repository.list_workspaces()

    def get_workspace(self, workspace_id: str) -> WorkspaceDefinition:
        return self.repositories.workspace_repository.get_workspace(workspace_id)

    def upsert_workspace(self, payload: Mapping[str, Any] | WorkspaceDefinition) -> WorkspaceDefinition:
        workspace = payload if isinstance(payload, WorkspaceDefinition) else WorkspaceDefinition.from_dict(payload)
        if not workspace.id:
            raise ValueError("workspace id is required")
        if not workspace.name:
            raise ValueError("workspace name is required")
        if not workspace.workflow_template_id:
            raise ValueError("workspace workflow_template_id is required")
        self.repositories.workspace_repository.get_workflow_template(workspace.workflow_template_id)
        self.validate_workspace(
            workspace,
            phase="save",
            error_code="workspace_validation_failed",
        )
        self.repositories.workspace_repository.upsert_workspace(workspace)
        return self.repositories.workspace_repository.get_workspace(workspace.id)

    def delete_workspace(self, workspace_id: str) -> None:
        self.repositories.workspace_repository.delete_workspace(workspace_id)

    def list_workflow_templates(self) -> list[WorkflowTemplate]:
        return self.repositories.workspace_repository.list_workflow_templates()

    def get_workflow_template(self, template_id: str) -> WorkflowTemplate:
        return self.repositories.workspace_repository.get_workflow_template(template_id)

    def upsert_workflow_template(self, payload: Mapping[str, Any] | WorkflowTemplate) -> WorkflowTemplate:
        workflow_template = payload if isinstance(payload, WorkflowTemplate) else WorkflowTemplate.from_dict(payload)
        if not workflow_template.id:
            raise ValueError("workflow template id is required")
        if not workflow_template.name:
            raise ValueError("workflow template name is required")
        self.repositories.workspace_repository.upsert_workflow_template(workflow_template)
        return self.repositories.workspace_repository.get_workflow_template(workflow_template.id)

    def delete_workflow_template(self, template_id: str) -> None:
        self.repositories.workspace_repository.delete_workflow_template(template_id)

    def list_connectors(self):
        return [descriptor for _, descriptor in self.registries.connector_registry.list_items()]

    def list_generations(self):
        return [descriptor for _, descriptor in self.registries.generation_registry.list_items()]

    def list_renderers(self):
        return [descriptor for _, descriptor in self.registries.renderer_registry.list_items()]

    def get_workspace_builder_catalog(self) -> dict[str, Any]:
        catalog = workspace_builder_catalog().to_dict()
        catalog["connectors"] = [_component_descriptor_payload(descriptor) for descriptor in self.list_connectors()]
        catalog["generations"] = [_component_descriptor_payload(descriptor) for descriptor in self.list_generations()]
        catalog["renderers"] = [_component_descriptor_payload(descriptor) for descriptor in self.list_renderers()]
        return catalog


@dataclass(slots=True)
class IdentityAccessService:
    repositories: BackendRepositories

    def list_users(self) -> list[UserRecord]:
        return self.repositories.auth_repository.list_users()

    def get_user(self, user_id: str) -> UserRecord:
        return self.repositories.auth_repository.get_user(user_id)

    def upsert_user(self, payload: Mapping[str, Any] | UserRecord) -> UserRecord:
        user = payload if isinstance(payload, UserRecord) else UserRecord.from_dict(payload)
        if not user.user_id:
            if not user.email:
                raise ValueError("email is required")
            try:
                existing_user = self.repositories.auth_repository.get_user_by_email(user.email)
                role_was_provided = True
                if isinstance(payload, Mapping):
                    role_was_provided = bool(str(payload.get("role") or "").strip())
                user.user_id = existing_user.user_id
                if not user.display_name:
                    user.display_name = existing_user.display_name
                if not user.allowed_workspace_ids:
                    user.allowed_workspace_ids = list(existing_user.allowed_workspace_ids)
                if not user.metadata:
                    user.metadata = dict(existing_user.metadata)
                if not role_was_provided:
                    user.role = existing_user.role
                user.created_at = existing_user.created_at
                user.is_active = existing_user.is_active
            except KeyError:
                user = UserRecord.create(
                    email=user.email,
                    display_name=user.display_name,
                    role=user.role,
                    allowed_workspace_ids=user.allowed_workspace_ids,
                    metadata=user.metadata,
                )
        if not user.email:
            raise ValueError("email is required")
        if user.role not in ALLOWED_USER_ROLES:
            raise ValueError(f"unsupported role: {user.role}")
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)
        return self.repositories.auth_repository.get_user(user.user_id)

    def delete_user(self, user_id: str) -> None:
        self.repositories.auth_repository.delete_user(user_id)

    def list_api_tokens(
        self,
        *,
        user_id: str = "",
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApiTokenRecord]:
        repository = self.repositories.auth_repository
        try:
            return repository.list_api_tokens(
                user_id=user_id,
                active_only=not include_inactive,
                limit=limit,
                offset=offset,
            )
        except TypeError:
            tokens = repository.list_api_tokens(user_id=user_id, active_only=not include_inactive)
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return tokens[normalized_offset : normalized_offset + normalized_limit]

    def issue_api_token(
        self,
        *,
        user_id: str,
        name: str,
        scopes: list[str] | None = None,
        expires_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[ApiTokenRecord, str]:
        user = self.repositories.auth_repository.get_user(user_id)
        if not user.is_active:
            raise ValueError(f"User '{user_id}' is inactive.")
        token_record, raw_token = issue_api_token(
            user_id=user.user_id,
            token_name=name,
            user_role=user.role,
            scopes=scopes,
            expires_at=expires_at,
            metadata=dict(metadata or {}),
        )
        self.repositories.auth_repository.upsert_api_token(token_record)
        return self.repositories.auth_repository.get_api_token(token_record.token_id), raw_token

    def revoke_api_token(self, token_id: str) -> ApiTokenRecord:
        token = self.repositories.auth_repository.get_api_token(token_id)
        token.is_active = False
        token.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_api_token(token)
        return self.repositories.auth_repository.get_api_token(token_id)

    def authenticate_access_token(self, raw_token: str) -> tuple[UserRecord, ApiTokenRecord]:
        token_text = str(raw_token or "").strip()
        if not token_text:
            raise PermissionError("Missing access token.")
        candidate_lookup = getattr(self.repositories.auth_repository, "list_api_tokens_for_value", None)
        candidate_tokens: list[ApiTokenRecord] = []
        if callable(candidate_lookup):
            candidate_tokens = list(candidate_lookup(token_text, active_only=True))
        tokens_to_check = candidate_tokens or self.repositories.auth_repository.list_api_tokens(active_only=True)
        for token in tokens_to_check:
            if not token.is_active or token_is_expired(token.expires_at):
                continue
            if not verify_token_value(token_text, token.token_hash):
                continue
            user = self.repositories.auth_repository.get_user(token.user_id)
            if not user.is_active:
                raise PermissionError("User is inactive.")
            token.last_used_at = utc_now_iso()
            token.updated_at = token.last_used_at
            self.repositories.auth_repository.upsert_api_token(token)
            return user, self.repositories.auth_repository.get_api_token(token.token_id)
        raise PermissionError("Invalid or expired access token.")

    def user_has_scope(self, token: ApiTokenRecord, required_scope: str) -> bool:
        return token_has_scope(token.scopes, required_scope)

    def user_can_access_workspace(self, user: UserRecord, workspace_id: str) -> bool:
        if user.role == ROLE_ADMIN:
            return True
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return False
        try:
            workspace = self.repositories.workspace_repository.get_workspace(normalized_workspace_id)
        except KeyError:
            return False
        if str(workspace.owner_user_id or "").strip() == str(user.user_id or "").strip():
            return True
        allowed = {str(item).strip() for item in user.allowed_workspace_ids if str(item).strip()}
        return normalized_workspace_id in allowed

    def user_can_access_run(self, user: UserRecord, run: RunRecord) -> bool:
        if user.role == ROLE_ADMIN:
            return True
        if str(run.normalized_user_id or "").strip() != str(user.user_id or "").strip():
            return False
        return self.user_can_access_workspace(user, run.workspace_id)

    def list_secrets(self, *, workspace_id: str = "", limit: int = 100, offset: int = 0) -> list[SecretRecord]:
        repository = self.repositories.secret_store
        try:
            return repository.list_secrets(workspace_id=workspace_id, limit=limit, offset=offset)
        except TypeError:
            secrets = repository.list_secrets(workspace_id=workspace_id)
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return secrets[normalized_offset : normalized_offset + normalized_limit]

    def get_secret(self, secret_id: str) -> SecretRecord:
        return self.repositories.secret_store.get_secret(secret_id)

    def upsert_secret(self, payload: Mapping[str, Any] | SecretRecord) -> SecretRecord:
        secret = payload if isinstance(payload, SecretRecord) else SecretRecord.from_dict(payload)
        existing_secret = None
        if secret.secret_id:
            try:
                existing_secret = self.repositories.secret_store.get_secret(secret.secret_id)
            except KeyError:
                existing_secret = None
        if not secret.secret_id:
            if not secret.name:
                raise ValueError("secret name is required")
            secret = SecretRecord.create(
                name=secret.name,
                provider=secret.provider,
                workspace_id=secret.workspace_id,
                description=secret.description,
                env_var_name=secret.env_var_name,
                secret_value=secret.secret_value,
                metadata=secret.metadata,
            )
        if not secret.name:
            raise ValueError("secret name is required")
        if secret.provider not in {SECRET_PROVIDER_STORED, SECRET_PROVIDER_ENV}:
            raise ValueError(f"unsupported secret provider: {secret.provider}")
        if existing_secret is not None:
            if not secret.secret_value and existing_secret.provider == SECRET_PROVIDER_STORED:
                secret.secret_value = existing_secret.secret_value
            if not secret.env_var_name and existing_secret.provider == SECRET_PROVIDER_ENV:
                secret.env_var_name = existing_secret.env_var_name
        if secret.provider == SECRET_PROVIDER_ENV and not secret.env_var_name:
            raise ValueError("env_var_name is required for env secrets")
        if secret.provider == SECRET_PROVIDER_STORED and not secret.secret_value:
            raise ValueError("secret_value is required for stored secrets")
        secret.updated_at = utc_now_iso()
        self.repositories.secret_store.upsert_secret(secret)
        return self.repositories.secret_store.get_secret(secret.secret_id)

    def delete_secret(self, secret_id: str) -> None:
        self.repositories.secret_store.delete_secret(secret_id)

    def resolve_secret_value(self, secret_id: str) -> str:
        secret = self.repositories.secret_store.get_secret(secret_id)
        return resolve_secret_references(f"${{secret:{secret.secret_id}}}", secret_lookup=self.repositories.secret_store.get_secret)

    def resolve_runtime_value(self, payload: Any) -> Any:
        return resolve_secret_references(payload, secret_lookup=self.repositories.secret_store.get_secret)


def _component_descriptor_payload(descriptor) -> dict[str, Any]:
    return {
        "id": descriptor.id,
        "kind": descriptor.kind,
        "name": descriptor.name,
        "description": descriptor.description,
        "metadata": dict(descriptor.metadata),
    }
