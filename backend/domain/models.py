from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from backend.domain.phase0_contracts import normalize_referral_relationship


RUN_STATUS_PLANNED = "planned"
RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_CANCEL_REQUESTED = "cancel_requested"
RUN_STATUS_CANCELLED = "cancelled"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"

STAGE_STATUS_PENDING = "pending"
STAGE_STATUS_SKIPPED = "skipped"
STAGE_STATUS_CANCELLED = "cancelled"
STAGE_STATUS_COMPLETED = "completed"
STAGE_STATUS_FAILED = "failed"

ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_REVIEWER = "reviewer"
ROLE_VIEWER = "viewer"

TOKEN_SCOPE_ADMIN = "admin"
TOKEN_SCOPE_WORKSPACES_READ = "workspaces:read"
TOKEN_SCOPE_WORKSPACES_WRITE = "workspaces:write"
TOKEN_SCOPE_TEMPLATES_READ = "templates:read"
TOKEN_SCOPE_TEMPLATES_WRITE = "templates:write"
TOKEN_SCOPE_RUNS_READ = "runs:read"
TOKEN_SCOPE_RUNS_WRITE = "runs:write"
TOKEN_SCOPE_WORKER_EXECUTE = "worker:execute"
TOKEN_SCOPE_REVIEWS_READ = "reviews:read"
TOKEN_SCOPE_REVIEWS_WRITE = "reviews:write"
TOKEN_SCOPE_ARTIFACTS_READ = "artifacts:read"
TOKEN_SCOPE_ARTIFACTS_WRITE = "artifacts:write"
TOKEN_SCOPE_SECRETS_READ = "secrets:read"
TOKEN_SCOPE_SECRETS_WRITE = "secrets:write"
TOKEN_SCOPE_USERS_READ = "users:read"
TOKEN_SCOPE_USERS_WRITE = "users:write"

SECRET_PROVIDER_STORED = "stored"
SECRET_PROVIDER_ENV = "env"

WORKER_STATUS_IDLE = "idle"
WORKER_STATUS_RUNNING = "running"
WORKER_STATUS_STOPPED = "stopped"
WORKER_STATUS_STALE = "stale"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_plus_seconds(seconds: int | float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0.0, float(seconds)))).isoformat()


@dataclass(slots=True)
class JobRecord:
    job_id: str
    title: str = ""
    company: str = ""
    source_type: str = ""
    filter_status: str = ""
    location_raw: str = ""
    link: str = ""
    source_url: str = ""
    apply_link: str = ""
    portal: str = ""
    description_text: str = ""
    manual_approved: bool = False
    role_category_id: str = ""
    role_category_name: str = ""
    priority_rank: int | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, record: Mapping[str, Any]) -> "JobRecord":
        payload = dict(record)
        known_field_names = {field_info.name for field_info in fields(cls) if field_info.name != "extra_fields"}
        extra_fields = {key: value for key, value in payload.items() if key not in known_field_names}

        description_text = str(
            payload.get("description_text")
            or payload.get("full_description")
            or payload.get("description")
            or ""
        )

        return cls(
            job_id=str(payload.get("job_id") or ""),
            title=str(payload.get("title") or ""),
            company=str(payload.get("company") or ""),
            source_type=str(payload.get("source_type") or ""),
            filter_status=str(payload.get("filter_status") or ""),
            location_raw=str(payload.get("location_raw") or ""),
            link=str(payload.get("link") or ""),
            source_url=str(payload.get("source_url") or ""),
            apply_link=str(payload.get("apply_link") or ""),
            portal=str(payload.get("portal") or ""),
            description_text=description_text,
            manual_approved=bool(payload.get("manual_approved") or False),
            role_category_id=str(payload.get("role_category_id") or ""),
            role_category_name=str(payload.get("role_category_name") or ""),
            priority_rank=payload.get("priority_rank"),
            extra_fields=extra_fields,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        extra_fields = payload.pop("extra_fields", {}) or {}
        payload.update(extra_fields)
        if self.description_text:
            payload.setdefault("description", self.description_text)
            payload.setdefault("full_description", self.description_text)
        return payload


@dataclass(slots=True)
class JobSource:
    id: str
    connector_id: str
    enabled: bool = True
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobSource":
        return cls(
            id=str(payload.get("id") or ""),
            connector_id=str(payload.get("connector_id") or ""),
            enabled=bool(payload.get("enabled", True)),
            settings=dict(payload.get("settings") or {}),
        )


@dataclass(slots=True)
class ProfileRef:
    id: str
    label: str
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProfileRef":
        return cls(
            id=str(payload.get("id") or ""),
            label=str(payload.get("label") or ""),
            settings=dict(payload.get("settings") or {}),
        )


@dataclass(slots=True)
class PromptSetRef:
    id: str
    family: str
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PromptSetRef":
        return cls(
            id=str(payload.get("id") or ""),
            family=str(payload.get("family") or ""),
            settings=dict(payload.get("settings") or {}),
        )


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    artifact_type: str
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRecord":
        return cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_type=str(payload.get("artifact_type") or ""),
            path=str(payload.get("path") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class ReviewRecord:
    review_id: str
    run_id: str
    job_id: str
    status: str = "pending"
    decision: str = ""
    reviewer: str = ""
    notes: str = ""
    job_set_key: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        job_id: str,
        status: str = "pending",
        decision: str = "",
        reviewer: str = "",
        notes: str = "",
        job_set_key: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "ReviewRecord":
        now = utc_now_iso()
        return cls(
            review_id=f"review_{uuid4().hex[:16]}",
            run_id=run_id,
            job_id=job_id,
            status=status,
            decision=decision,
            reviewer=reviewer,
            notes=notes,
            job_set_key=job_set_key,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReviewRecord":
        return cls(
            review_id=str(payload.get("review_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            job_id=str(payload.get("job_id") or ""),
            status=str(payload.get("status") or "pending"),
            decision=str(payload.get("decision") or ""),
            reviewer=str(payload.get("reviewer") or ""),
            notes=str(payload.get("notes") or ""),
            job_set_key=str(payload.get("job_set_key") or ""),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class ReferralContactRecord:
    contact_id: str
    name: str
    company: str
    linkedin_url: str = ""
    relationship_note: str = ""
    can_refer: bool = False
    is_active: bool = True
    inactive_at: str = ""
    inactive_reason: str = ""
    companies: list[dict[str, Any]] = field(default_factory=list)
    source_kind: str = "manual"
    import_batch_id: str = ""
    import_ref: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        company: str = "",
        companies: list[Mapping[str, Any]] | None = None,
        linkedin_url: str = "",
        relationship_note: str = "",
        can_refer: bool = False,
        is_active: bool = True,
        inactive_at: str = "",
        inactive_reason: str = "",
        source_kind: str = "manual",
        import_batch_id: str = "",
        import_ref: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "ReferralContactRecord":
        now = utc_now_iso()
        normalized = normalize_referral_relationship(
            {
                "name": name,
                "company": company,
                "companies": companies or [],
                "linkedin_url": linkedin_url,
                "relationship_note": relationship_note,
                "can_refer": can_refer,
                "is_active": is_active,
                "inactive_at": inactive_at,
                "inactive_reason": inactive_reason,
                "source_kind": source_kind,
                "import_batch_id": import_batch_id,
                "import_ref": import_ref,
                "metadata": dict(metadata or {}),
            }
        )
        normalized_companies = [dict(item) for item in normalized["companies"]]
        primary_company = next(
            (
                str(item.get("company_name") or "").strip()
                for item in normalized_companies
                if str(item.get("company_name") or "").strip()
            ),
            str(company).strip(),
        )
        return cls(
            contact_id=f"contact_{uuid4().hex[:16]}",
            name=str(normalized["person"]["full_name"] or name).strip(),
            company=primary_company,
            linkedin_url=str(normalized["person"]["linkedin_url"] or "").strip(),
            relationship_note=str(normalized["person"]["notes"] or "").strip(),
            can_refer=bool(
                can_refer
                or any(bool(item.get("can_refer")) for item in normalized_companies)
            ),
            is_active=bool(normalized["lifecycle"]["is_active"]),
            inactive_at=str(normalized["lifecycle"]["inactive_at"] or "").strip(),
            inactive_reason=str(normalized["lifecycle"]["inactive_reason"] or "").strip(),
            companies=normalized_companies,
            source_kind=str(normalized["source"]["kind"] or source_kind).strip() or "manual",
            import_batch_id=str(normalized["source"]["import_batch_id"] or import_batch_id).strip(),
            import_ref=str(normalized["source"]["import_ref"] or import_ref).strip(),
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["company"] = self.primary_company()
        payload["can_refer"] = self.can_refer or any(bool(item.get("can_refer")) for item in self.companies)
        payload["is_active"] = bool(self.is_active)
        payload["lifecycle"] = {
            "status": "active" if self.is_active else "inactive",
            "is_active": bool(self.is_active),
            "inactive_at": self.inactive_at,
            "inactive_reason": self.inactive_reason,
        }
        return payload

    def primary_company(self) -> str:
        for item in self.companies:
            company_name = str(item.get("company_name") or "").strip()
            if company_name:
                return company_name
        return str(self.company or "").strip()

    def company_names(self) -> list[str]:
        names: list[str] = []
        for item in self.companies:
            company_name = str(item.get("company_name") or "").strip()
            if company_name:
                names.append(company_name)
        if not names and str(self.company or "").strip():
            names.append(str(self.company).strip())
        return names

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferralContactRecord":
        normalized = normalize_referral_relationship(payload)
        companies = [dict(item) for item in normalized["companies"]]
        primary_company = next(
            (
                str(item.get("company_name") or "").strip()
                for item in companies
                if str(item.get("company_name") or "").strip()
            ),
            str(payload.get("company") or "").strip(),
        )
        return cls(
            contact_id=str(payload.get("contact_id") or ""),
            name=str(normalized["person"]["full_name"] or payload.get("name") or ""),
            company=primary_company,
            linkedin_url=str(normalized["person"]["linkedin_url"] or ""),
            relationship_note=str(normalized["person"]["notes"] or ""),
            can_refer=bool(
                payload.get("can_refer")
                or any(bool(item.get("can_refer")) for item in companies)
            ),
            is_active=bool(normalized["lifecycle"]["is_active"]),
            inactive_at=str(normalized["lifecycle"]["inactive_at"] or ""),
            inactive_reason=str(normalized["lifecycle"]["inactive_reason"] or ""),
            companies=companies,
            source_kind=str(normalized["source"]["kind"] or payload.get("source_kind") or "manual"),
            import_batch_id=str(normalized["source"]["import_batch_id"] or payload.get("import_batch_id") or ""),
            import_ref=str(normalized["source"]["import_ref"] or payload.get("import_ref") or ""),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class UserRecord:
    user_id: str
    email: str
    display_name: str = ""
    role: str = ROLE_VIEWER
    allowed_workspace_ids: list[str] = field(default_factory=list)
    is_active: bool = True
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        email: str,
        display_name: str = "",
        role: str = ROLE_VIEWER,
        allowed_workspace_ids: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "UserRecord":
        now = utc_now_iso()
        return cls(
            user_id=f"user_{uuid4().hex[:16]}",
            email=str(email).strip(),
            display_name=str(display_name).strip(),
            role=str(role or ROLE_VIEWER).strip() or ROLE_VIEWER,
            allowed_workspace_ids=[str(item).strip() for item in (allowed_workspace_ids or []) if str(item).strip()],
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UserRecord":
        return cls(
            user_id=str(payload.get("user_id") or ""),
            email=str(payload.get("email") or ""),
            display_name=str(payload.get("display_name") or ""),
            role=str(payload.get("role") or ROLE_VIEWER),
            allowed_workspace_ids=[
                str(item) for item in payload.get("allowed_workspace_ids") or [] if str(item).strip()
            ],
            is_active=bool(payload.get("is_active", True)),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class ApiTokenRecord:
    token_id: str
    user_id: str
    name: str
    token_prefix: str
    token_hash: str
    scopes: list[str] = field(default_factory=list)
    is_active: bool = True
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    last_used_at: str = ""
    expires_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        name: str,
        token_prefix: str,
        token_hash: str,
        scopes: list[str] | None = None,
        expires_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "ApiTokenRecord":
        now = utc_now_iso()
        return cls(
            token_id=f"token_{uuid4().hex[:16]}",
            user_id=str(user_id).strip(),
            name=str(name).strip(),
            token_prefix=str(token_prefix).strip(),
            token_hash=str(token_hash).strip(),
            scopes=[str(item).strip() for item in (scopes or []) if str(item).strip()],
            created_at=now,
            updated_at=now,
            expires_at=str(expires_at).strip(),
            metadata=dict(metadata or {}),
        )

    def to_storage_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "name": self.name,
            "token_prefix": self.token_prefix,
            "scopes": list(self.scopes),
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "expires_at": self.expires_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ApiTokenRecord":
        return cls(
            token_id=str(payload.get("token_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            name=str(payload.get("name") or ""),
            token_prefix=str(payload.get("token_prefix") or ""),
            token_hash=str(payload.get("token_hash") or ""),
            scopes=[str(item) for item in payload.get("scopes") or [] if str(item).strip()],
            is_active=bool(payload.get("is_active", True)),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            last_used_at=str(payload.get("last_used_at") or ""),
            expires_at=str(payload.get("expires_at") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class SecretRecord:
    secret_id: str
    name: str
    provider: str = SECRET_PROVIDER_STORED
    workspace_id: str = ""
    description: str = ""
    env_var_name: str = ""
    secret_value: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        provider: str = SECRET_PROVIDER_STORED,
        workspace_id: str = "",
        description: str = "",
        env_var_name: str = "",
        secret_value: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "SecretRecord":
        now = utc_now_iso()
        return cls(
            secret_id=f"secret_{uuid4().hex[:16]}",
            name=str(name).strip(),
            provider=str(provider or SECRET_PROVIDER_STORED).strip() or SECRET_PROVIDER_STORED,
            workspace_id=str(workspace_id).strip(),
            description=str(description).strip(),
            env_var_name=str(env_var_name).strip(),
            secret_value=str(secret_value),
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    def to_storage_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "secret_id": self.secret_id,
            "name": self.name,
            "provider": self.provider,
            "workspace_id": self.workspace_id,
            "description": self.description,
            "env_var_name": self.env_var_name,
            "has_stored_value": bool(self.secret_value),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SecretRecord":
        return cls(
            secret_id=str(payload.get("secret_id") or ""),
            name=str(payload.get("name") or ""),
            provider=str(payload.get("provider") or SECRET_PROVIDER_STORED),
            workspace_id=str(payload.get("workspace_id") or ""),
            description=str(payload.get("description") or ""),
            env_var_name=str(payload.get("env_var_name") or ""),
            secret_value=str(payload.get("secret_value") or ""),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class WorkerRecord:
    worker_id: str
    status: str = WORKER_STATUS_IDLE
    host_name: str = ""
    process_id: int = 0
    current_run_id: str = ""
    started_at: str = field(default_factory=utc_now_iso)
    last_heartbeat_at: str = field(default_factory=utc_now_iso)
    lease_expires_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        status: str = WORKER_STATUS_IDLE,
        host_name: str = "",
        process_id: int = 0,
        current_run_id: str = "",
        lease_expires_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "WorkerRecord":
        now = utc_now_iso()
        return cls(
            worker_id=str(worker_id).strip(),
            status=str(status or WORKER_STATUS_IDLE).strip() or WORKER_STATUS_IDLE,
            host_name=str(host_name).strip(),
            process_id=int(process_id or 0),
            current_run_id=str(current_run_id).strip(),
            started_at=now,
            last_heartbeat_at=now,
            lease_expires_at=str(lease_expires_at).strip(),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkerRecord":
        return cls(
            worker_id=str(payload.get("worker_id") or ""),
            status=str(payload.get("status") or WORKER_STATUS_IDLE),
            host_name=str(payload.get("host_name") or ""),
            process_id=int(payload.get("process_id") or 0),
            current_run_id=str(payload.get("current_run_id") or ""),
            started_at=str(payload.get("started_at") or utc_now_iso()),
            last_heartbeat_at=str(payload.get("last_heartbeat_at") or utc_now_iso()),
            lease_expires_at=str(payload.get("lease_expires_at") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class StageDefinition:
    stage_id: str
    stage_type: str
    name: str
    description: str = ""
    input_keys: list[str] = field(default_factory=list)
    output_key: str = ""
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StageDefinition":
        return cls(
            stage_id=str(payload.get("stage_id") or ""),
            stage_type=str(payload.get("stage_type") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            input_keys=[str(item) for item in payload.get("input_keys") or [] if str(item).strip()],
            output_key=str(payload.get("output_key") or ""),
            enabled=bool(payload.get("enabled", True)),
            config=dict(payload.get("config") or {}),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class WorkflowTemplate:
    id: str
    name: str
    description: str = ""
    stages: list[StageDefinition] = field(default_factory=list)
    default_run_settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "stages": [stage.to_dict() for stage in self.stages],
            "default_run_settings": dict(self.default_run_settings),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkflowTemplate":
        return cls(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            stages=[StageDefinition.from_dict(item) for item in payload.get("stages") or [] if isinstance(item, dict)],
            default_run_settings=dict(payload.get("default_run_settings") or {}),
        )


@dataclass(slots=True)
class WorkspaceDefinition:
    id: str
    name: str
    workflow_template_id: str
    description: str = ""
    workspace_type: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    feature_flags: dict[str, bool] = field(default_factory=dict)
    profiles: list[ProfileRef] = field(default_factory=list)
    prompt_sets: list[PromptSetRef] = field(default_factory=list)
    sources: list[JobSource] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "workflow_template_id": self.workflow_template_id,
            "description": self.description,
            "workspace_type": self.workspace_type,
            "settings": dict(self.settings),
            "feature_flags": dict(self.feature_flags),
            "profiles": [asdict(profile) for profile in self.profiles],
            "prompt_sets": [asdict(prompt_set) for prompt_set in self.prompt_sets],
            "sources": [asdict(source) for source in self.sources],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkspaceDefinition":
        return cls(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            workflow_template_id=str(payload.get("workflow_template_id") or ""),
            description=str(payload.get("description") or ""),
            workspace_type=str(payload.get("workspace_type") or ""),
            settings=dict(payload.get("settings") or {}),
            feature_flags={str(key): bool(value) for key, value in (payload.get("feature_flags") or {}).items()},
            profiles=[ProfileRef.from_dict(item) for item in payload.get("profiles") or [] if isinstance(item, dict)],
            prompt_sets=[
                PromptSetRef.from_dict(item) for item in payload.get("prompt_sets") or [] if isinstance(item, dict)
            ],
            sources=[JobSource.from_dict(item) for item in payload.get("sources") or [] if isinstance(item, dict)],
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class RunPlan:
    workflow_template_id: str
    workspace_snapshot: dict[str, Any]
    workflow_snapshot: dict[str, Any]
    resolved_run_settings: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunPlan":
        return cls(
            workflow_template_id=str(payload.get("workflow_template_id") or ""),
            workspace_snapshot=dict(payload.get("workspace_snapshot") or {}),
            workflow_snapshot=dict(payload.get("workflow_snapshot") or {}),
            resolved_run_settings=dict(payload.get("resolved_run_settings") or {}),
            created_at=str(payload.get("created_at") or utc_now_iso()),
        )


@dataclass(slots=True)
class StageResult:
    stage_id: str
    stage_type: str
    status: str
    started_at: str
    finished_at: str
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    output_keys: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StageResult":
        return cls(
            stage_id=str(payload.get("stage_id") or ""),
            stage_type=str(payload.get("stage_type") or ""),
            status=str(payload.get("status") or ""),
            started_at=str(payload.get("started_at") or ""),
            finished_at=str(payload.get("finished_at") or ""),
            metrics=dict(payload.get("metrics") or {}),
            error=str(payload.get("error") or ""),
            output_keys=[str(item) for item in payload.get("output_keys") or [] if str(item).strip()],
            artifact_ids=[str(item) for item in payload.get("artifact_ids") or [] if str(item).strip()],
        )


def resolve_run_user_id(requested_by: str, user_id: str = "") -> str:
    normalized_requested_by = str(requested_by or "").strip()
    if normalized_requested_by.startswith("api:"):
        return normalized_requested_by.split(":", 1)[1].strip()
    return str(user_id or "").strip()


@dataclass(slots=True)
class RunRecord:
    id: str
    workspace_id: str
    workflow_template_id: str
    status: str
    requested_by: str = ""
    user_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    current_stage_id: str = ""
    last_error: str = ""
    attempt_count: int = 0
    max_attempts: int = 1
    run_input_overrides: dict[str, Any] = field(default_factory=dict)
    run_plan: RunPlan | None = None
    stage_results: list[StageResult] = field(default_factory=list)
    final_job_set_keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        workspace_id: str,
        workflow_template_id: str,
        run_input_overrides: Mapping[str, Any] | None = None,
        requested_by: str = "",
        max_attempts: int = 1,
        metadata: Mapping[str, Any] | None = None,
    ) -> "RunRecord":
        now = utc_now_iso()
        return cls(
            id=f"run_{uuid4().hex[:16]}",
            workspace_id=workspace_id,
            workflow_template_id=workflow_template_id,
            status=RUN_STATUS_PLANNED,
            requested_by=requested_by,
            user_id=resolve_run_user_id(requested_by),
            created_at=now,
            updated_at=now,
            max_attempts=max(1, int(max_attempts)),
            run_input_overrides=dict(run_input_overrides or {}),
            metadata=dict(metadata or {}),
        )

    @property
    def normalized_user_id(self) -> str:
        return resolve_run_user_id(self.requested_by, self.user_id)

    @property
    def is_test_run(self) -> bool:
        if str(self.metadata.get("run_mode") or "").strip().lower() == "test":
            return True
        if self.run_plan is None:
            return False
        return str(self.run_plan.resolved_run_settings.get("run_mode") or "").strip().lower() == "test"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "workflow_template_id": self.workflow_template_id,
            "status": self.status,
            "requested_by": self.requested_by,
            "user_id": self.normalized_user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_stage_id": self.current_stage_id,
            "last_error": self.last_error,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "run_input_overrides": dict(self.run_input_overrides),
            "run_plan": self.run_plan.to_dict() if self.run_plan else None,
            "stage_results": [result.to_dict() for result in self.stage_results],
            "final_job_set_keys": list(self.final_job_set_keys),
            "metadata": dict(self.metadata),
            "is_test_run": self.is_test_run,
            "run_mode": "test" if self.is_test_run else "normal",
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunRecord":
        run_plan_payload = payload.get("run_plan")
        requested_by = str(payload.get("requested_by") or "")
        return cls(
            id=str(payload.get("id") or ""),
            workspace_id=str(payload.get("workspace_id") or ""),
            workflow_template_id=str(payload.get("workflow_template_id") or ""),
            status=str(payload.get("status") or RUN_STATUS_PLANNED),
            requested_by=requested_by,
            user_id=resolve_run_user_id(requested_by, str(payload.get("user_id") or "")),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            queued_at=str(payload.get("queued_at") or ""),
            started_at=str(payload.get("started_at") or ""),
            finished_at=str(payload.get("finished_at") or ""),
            current_stage_id=str(payload.get("current_stage_id") or ""),
            last_error=str(payload.get("last_error") or ""),
            attempt_count=int(payload.get("attempt_count") or 0),
            max_attempts=max(1, int(payload.get("max_attempts") or 1)),
            run_input_overrides=dict(payload.get("run_input_overrides") or {}),
            run_plan=RunPlan.from_dict(run_plan_payload) if isinstance(run_plan_payload, dict) else None,
            stage_results=[
                StageResult.from_dict(item) for item in payload.get("stage_results") or [] if isinstance(item, dict)
            ],
            final_job_set_keys=[str(item) for item in payload.get("final_job_set_keys") or [] if str(item).strip()],
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class StageContext:
    workspace: WorkspaceDefinition
    workflow: WorkflowTemplate
    run: RunRecord
    repositories: Any
    registries: Any
    logger: Any
    job_sets: dict[str, list[JobRecord]] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactRecord] = field(default_factory=list)

    def get_job_set(self, key: str) -> list[JobRecord]:
        return list(self.job_sets.get(key) or [])

    def get_job_dicts(self, key: str) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.get_job_set(key)]

    def set_job_set(self, key: str, jobs: list[JobRecord | Mapping[str, Any]]) -> None:
        self.job_sets[key] = [
            item if isinstance(item, JobRecord) else JobRecord.from_mapping(item)
            for item in jobs
        ]

    def update_run_progress(
        self,
        *,
        stage_id: str,
        stage_type: str = "",
        stage_name: str = "",
        message: str = "",
        counters: Mapping[str, Any] | None = None,
        current_item: Mapping[str, Any] | None = None,
        recent_failures: list[Mapping[str, Any]] | None = None,
        status: str = "running",
        extra: Mapping[str, Any] | None = None,
        save: bool = True,
    ) -> None:
        now = utc_now_iso()
        progress_payload = {
            "stage_id": str(stage_id or self.run.current_stage_id or ""),
            "stage_type": str(stage_type or ""),
            "stage_name": str(stage_name or ""),
            "status": str(status or "running"),
            "message": str(message or ""),
            "started_at": str(
                (
                    (self.run.metadata.get("progress") or {}).get("started_at")
                    if isinstance(self.run.metadata.get("progress"), dict)
                    else ""
                )
                or now
            ),
            "last_progress_at": now,
            "counters": dict(counters or {}),
            "current_item": dict(current_item or {}),
            "recent_failures": [dict(item) for item in recent_failures or [] if item is not None],
        }
        if extra:
            progress_payload.update(dict(extra))
        self.run.metadata["progress"] = progress_payload
        self.run.updated_at = now
        if save:
            self.repositories.run_repository.save(self.run)

    def clear_run_progress(self, *, save: bool = True) -> None:
        self.run.metadata.pop("progress", None)
        self.run.updated_at = utc_now_iso()
        if save:
            self.repositories.run_repository.save(self.run)
