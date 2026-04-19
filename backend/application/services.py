from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from backend.capabilities.networking import (
    build_hiring_manager_outreach_draft,
    build_referral_outreach_draft,
    find_referral_contacts_for_company,
    guess_hiring_manager_from_job,
)
from backend.domain.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_REVIEWER,
    ROLE_VIEWER,
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    SECRET_PROVIDER_ENV,
    SECRET_PROVIDER_STORED,
    WORKER_STATUS_IDLE,
    WORKER_STATUS_RUNNING,
    WORKER_STATUS_STALE,
    WORKER_STATUS_STOPPED,
    ArtifactRecord,
    ApiTokenRecord,
    JobRecord,
    ReferralContactRecord,
    ReviewRecord,
    RunRecord,
    SecretRecord,
    StageContext,
    UserRecord,
    WorkerRecord,
    WorkflowTemplate,
    WorkspaceDefinition,
    utc_plus_seconds,
    utc_now_iso,
)
from backend.orchestration import build_workspace_from_scratch, workspace_builder_catalog
from backend.security import issue_api_token, resolve_secret_references, token_has_scope, token_is_expired, verify_token_value


ALLOWED_USER_ROLES = {ROLE_ADMIN, ROLE_EDITOR, ROLE_REVIEWER, ROLE_VIEWER}


@dataclass(slots=True)
class BackendApplication:
    repositories: Any
    registries: Any
    stage_engine: Any

    def list_workspaces(self):
        return self.repositories.workspace_repository.list_workspaces()

    def get_workspace(self, workspace_id: str):
        return self.repositories.workspace_repository.get_workspace(workspace_id)

    def upsert_workspace(self, payload: Mapping[str, Any] | WorkspaceDefinition):
        workspace = payload if isinstance(payload, WorkspaceDefinition) else WorkspaceDefinition.from_dict(payload)
        if not workspace.id:
            raise ValueError("workspace id is required")
        if not workspace.name:
            raise ValueError("workspace name is required")
        if not workspace.workflow_template_id:
            raise ValueError("workspace workflow_template_id is required")
        self.repositories.workspace_repository.get_workflow_template(workspace.workflow_template_id)
        self.repositories.workspace_repository.upsert_workspace(workspace)
        return self.repositories.workspace_repository.get_workspace(workspace.id)

    def delete_workspace(self, workspace_id: str) -> None:
        self.repositories.workspace_repository.delete_workspace(workspace_id)

    def list_workflow_templates(self):
        return self.repositories.workspace_repository.list_workflow_templates()

    def get_workflow_template(self, template_id: str):
        return self.repositories.workspace_repository.get_workflow_template(template_id)

    def upsert_workflow_template(self, payload: Mapping[str, Any] | WorkflowTemplate):
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
        catalog["connectors"] = [
            {
                "id": descriptor.id,
                "kind": descriptor.kind,
                "name": descriptor.name,
                "description": descriptor.description,
                "metadata": dict(descriptor.metadata),
            }
            for descriptor in self.list_connectors()
        ]
        catalog["generations"] = [
            {
                "id": descriptor.id,
                "kind": descriptor.kind,
                "name": descriptor.name,
                "description": descriptor.description,
                "metadata": dict(descriptor.metadata),
            }
            for descriptor in self.list_generations()
        ]
        catalog["renderers"] = [
            {
                "id": descriptor.id,
                "kind": descriptor.kind,
                "name": descriptor.name,
                "description": descriptor.description,
                "metadata": dict(descriptor.metadata),
            }
            for descriptor in self.list_renderers()
        ]
        return catalog

    def create_workspace_from_scratch(self, payload: Mapping[str, Any]) -> WorkspaceDefinition:
        workflow_template, workspace = build_workspace_from_scratch(dict(payload))
        self.upsert_workflow_template(workflow_template)
        return self.upsert_workspace(workspace)

    def update_workspace_from_scratch(self, workspace_id: str, payload: Mapping[str, Any]) -> WorkspaceDefinition:
        existing_workspace = self.get_workspace(workspace_id)
        builder_payload = dict(payload)
        builder_payload["workspace_id"] = existing_workspace.id
        builder_payload.setdefault("workflow_template_id", existing_workspace.workflow_template_id)
        workflow_template, workspace = build_workspace_from_scratch(builder_payload)
        self.upsert_workflow_template(workflow_template)
        return self.upsert_workspace(workspace)

    def list_users(self) -> list[UserRecord]:
        return self.repositories.auth_repository.list_users()

    def get_user(self, user_id: str) -> UserRecord:
        return self.repositories.auth_repository.get_user(user_id)

    def upsert_user(self, payload: Mapping[str, Any] | UserRecord):
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

    def list_referral_contacts(self, user_id: str) -> list[ReferralContactRecord]:
        user = self.repositories.auth_repository.get_user(user_id)
        contacts = [
            ReferralContactRecord.from_dict(item)
            for item in (user.metadata or {}).get("referrals") or []
            if isinstance(item, dict)
        ]
        contacts.sort(key=lambda item: (item.company.lower(), item.name.lower()))
        return contacts

    def get_referral_contact(self, user_id: str, contact_id: str) -> ReferralContactRecord:
        for contact in self.list_referral_contacts(user_id):
            if contact.contact_id == contact_id:
                return contact
        raise KeyError(f"Referral contact '{contact_id}' not found.")

    def upsert_referral_contact(
        self,
        *,
        user_id: str,
        payload: Mapping[str, Any] | ReferralContactRecord,
        contact_id: str = "",
    ) -> ReferralContactRecord:
        user = self.repositories.auth_repository.get_user(user_id)
        contact = payload if isinstance(payload, ReferralContactRecord) else ReferralContactRecord.from_dict(payload)
        if contact_id:
            contact.contact_id = contact_id
        if not contact.contact_id:
            contact = ReferralContactRecord.create(
                name=contact.name,
                company=contact.company,
                linkedin_url=contact.linkedin_url,
                relationship_note=contact.relationship_note,
                can_refer=contact.can_refer,
                metadata=contact.metadata,
            )
        if not contact.name:
            raise ValueError("contact name is required")
        if not contact.company:
            raise ValueError("contact company is required")
        contact.updated_at = utc_now_iso()

        contacts = self.list_referral_contacts(user_id)
        replaced = False
        normalized_contacts: list[ReferralContactRecord] = []
        for existing in contacts:
            if existing.contact_id == contact.contact_id:
                normalized_contacts.append(contact)
                replaced = True
            else:
                normalized_contacts.append(existing)
        if not replaced:
            normalized_contacts.append(contact)
        self._persist_referral_contacts(user, normalized_contacts)
        return self.get_referral_contact(user_id, contact.contact_id)

    def delete_referral_contact(self, user_id: str, contact_id: str) -> None:
        user = self.repositories.auth_repository.get_user(user_id)
        contacts = self.list_referral_contacts(user_id)
        kept_contacts = [contact for contact in contacts if contact.contact_id != contact_id]
        if len(kept_contacts) == len(contacts):
            raise KeyError(f"Referral contact '{contact_id}' not found.")
        self._persist_referral_contacts(user, kept_contacts)

    def generate_referral_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
        contact_id: str = "",
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self._get_job_for_run(run_id=run_id, job_id=job_id)
        contacts = self.list_referral_contacts(user_id)
        matches = find_referral_contacts_for_company(contacts, job.company)
        if contact_id:
            contact = next((item for item in matches if item.contact_id == contact_id), None)
            if contact is None:
                contact = self.get_referral_contact(user_id, contact_id)
        else:
            contact = matches[0] if matches else None
        if contact is None:
            raise ValueError("No referral contact matches this job yet.")
        profile = dict((user.metadata or {}).get("profile") or {})
        payload = build_referral_outreach_draft(profile=profile, job=job, contact=contact)
        payload["matched_contacts"] = [item.to_dict() for item in matches]
        return payload

    def generate_hiring_manager_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self._get_job_for_run(run_id=run_id, job_id=job_id)
        profile = dict((user.metadata or {}).get("profile") or {})
        hiring_manager = guess_hiring_manager_from_job(job)
        return build_hiring_manager_outreach_draft(
            profile=profile,
            job=job,
            hiring_manager=hiring_manager,
        )

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
        for token in self.repositories.auth_repository.list_api_tokens(active_only=True):
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
        allowed = {item for item in user.allowed_workspace_ids if item}
        if not allowed:
            return True
        return workspace_id in allowed

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

    def upsert_secret(self, payload: Mapping[str, Any] | SecretRecord):
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

    def _persist_referral_contacts(self, user: UserRecord, contacts: list[ReferralContactRecord]) -> None:
        metadata = dict(user.metadata or {})
        metadata["referrals"] = [contact.to_dict() for contact in contacts]
        user.metadata = metadata
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)

    def _get_job_for_run(self, *, run_id: str, job_id: str) -> JobRecord:
        self.repositories.run_repository.get(run_id)
        for jobs in self.repositories.job_store.load_all_job_sets(run_id).values():
            for job in jobs:
                if job.job_id == job_id:
                    return job
        raise KeyError(f"Job '{job_id}' not found for run '{run_id}'.")

    def get_run(self, run_id: str) -> RunRecord:
        return self.repositories.run_repository.get(run_id)

    def delete_run(self, run_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        deletable_statuses = {
            RUN_STATUS_PLANNED,
            RUN_STATUS_QUEUED,
            RUN_STATUS_CANCELLED,
            RUN_STATUS_FAILED,
        }
        if run.status not in deletable_statuses:
            raise ValueError(
                "only planned, queued, failed, or cancelled runs can be deleted",
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
            runs = repository.list_runs(limit=max(1, int(limit)) + max(0, int(offset)), status=status, workspace_id=workspace_id)
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
        self._refresh_run_job_keys(run_id)
        return self.repositories.job_store.load_job_set(run_id, set_key)

    def delete_job_set(self, run_id: str, set_key: str) -> None:
        self.repositories.run_repository.get(run_id)
        self.repositories.job_store.delete_job_set(run_id, set_key)
        self._refresh_run_job_keys(run_id)

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
            reviews = repository.list_reviews(run_id=run_id, job_id=job_id, limit=max(1, int(limit)) + max(0, int(offset)))
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
        if not review.review_id:
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
        if review_id:
            review.review_id = review_id
        review.run_id = run_id
        review.updated_at = utc_now_iso()
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
                    run.status = RUN_STATUS_QUEUED
                    run.current_stage_id = ""
                    run.updated_at = now
                    run.last_error = "Recovered from expired worker lease."
                    self.repositories.run_repository.save(run)
            worker.status = WORKER_STATUS_STALE
            worker.current_run_id = ""
            worker.last_heartbeat_at = now
            worker.lease_expires_at = now
            self.repositories.worker_store.upsert_worker(worker)
            recovered.append(worker)
        return recovered

    def start_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        execute: bool = True,
        enqueue: bool = False,
        requested_by: str = "cli",
        max_attempts: int = 1,
    ) -> RunRecord:
        if execute and enqueue:
            raise ValueError("run cannot be both queued and synchronously executed")
        workspace = self.repositories.workspace_repository.get_workspace(workspace_id)
        workflow = self.repositories.workspace_repository.get_workflow_template(workspace.workflow_template_id)

        run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=workflow.id,
            run_input_overrides=run_input_overrides or {},
            requested_by=requested_by,
            max_attempts=max_attempts,
            metadata={"workspace_type": workspace.workspace_type},
        )
        run.run_plan = self.stage_engine.build_run_plan(
            workspace=workspace,
            workflow=workflow,
            run_input_overrides=run_input_overrides or {},
        )
        self.repositories.run_repository.save(run)

        if enqueue:
            return self._queue_run(run)
        if not execute:
            return self.repositories.run_repository.get(run.id)
        return self._execute_run(run, workspace=workspace, workflow=workflow, auto_retry_failed=False)

    def enqueue_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        requested_by: str = "api",
        max_attempts: int = 1,
    ) -> RunRecord:
        return self.start_run(
            workspace_id,
            run_input_overrides=run_input_overrides,
            execute=False,
            enqueue=True,
            requested_by=requested_by,
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
        workspace = self.repositories.workspace_repository.get_workspace(run.workspace_id)
        workflow = self.repositories.workspace_repository.get_workflow_template(run.workflow_template_id)
        return self._execute_run(run, workspace=workspace, workflow=workflow, auto_retry_failed=auto_retry_failed)

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
        run.updated_at = now
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def retry_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        if run.status not in {RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            raise ValueError("only failed or cancelled runs can be retried")
        self.repositories.job_store.clear_run(run.id)
        self.repositories.artifact_store.clear_run(run.id)
        run.stage_results = []
        run.final_job_set_keys = []
        run.current_stage_id = ""
        run.last_error = ""
        run.started_at = ""
        run.finished_at = ""
        return self._queue_run(run)

    def resume_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        if run.status not in {RUN_STATUS_PLANNED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            raise ValueError("only planned, failed, or cancelled runs can be resumed")
        self._trim_to_resumable_prefix(run)
        run.final_job_set_keys = sorted(self.repositories.job_store.list_job_set_keys(run.id))
        run.current_stage_id = ""
        run.last_error = ""
        run.started_at = ""
        run.finished_at = ""
        return self._queue_run(run)

    def _execute_run(
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
        except Exception:
            run = self.repositories.run_repository.get(run.id)
            if auto_retry_failed and run.status == RUN_STATUS_FAILED and run.attempt_count < run.max_attempts:
                self._trim_to_resumable_prefix(run)
                self._queue_run(run)
            return self.repositories.run_repository.get(run.id)
        return self.repositories.run_repository.get(run.id)

    def _queue_run(self, run: RunRecord) -> RunRecord:
        now = utc_now_iso()
        run.status = RUN_STATUS_QUEUED
        run.queued_at = now
        run.current_stage_id = ""
        run.started_at = ""
        run.finished_at = ""
        run.updated_at = now
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def _trim_to_resumable_prefix(self, run: RunRecord) -> None:
        kept_results = []
        for result in run.stage_results:
            if result.status in {"completed", "skipped"}:
                kept_results.append(result)
                continue
            break
        run.stage_results = kept_results

    def _refresh_run_job_keys(self, run_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        run.final_job_set_keys = sorted(self.repositories.job_store.list_job_set_keys(run.id))
        run.updated_at = utc_now_iso()
        self.repositories.run_repository.save(run)
