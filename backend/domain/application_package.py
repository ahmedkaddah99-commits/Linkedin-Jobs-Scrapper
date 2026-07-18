from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any, Mapping

APPLICATION_PACKAGE_ID_PREFIX = "aapkg_"
APPLICATION_PACKAGE_TTL_SECONDS = 30 * 60  # 30 min after launch
APPLICATION_PACKAGE_BINDING_TTL_SECONDS = 5 * 60  # 5 min to bind after launch
APPLICATION_PACKAGE_STATUS_CREATED = "created"
APPLICATION_PACKAGE_STATUS_LAUNCHED = "launched"
APPLICATION_PACKAGE_STATUS_BOUND = "bound"
APPLICATION_PACKAGE_STATUS_EXPIRED = "expired"
APPLICATION_PACKAGE_STATUS_CONSUMED = "consumed"

APPLICATION_PACKAGE_STATUSES = {
    APPLICATION_PACKAGE_STATUS_CREATED,
    APPLICATION_PACKAGE_STATUS_LAUNCHED,
    APPLICATION_PACKAGE_STATUS_BOUND,
    APPLICATION_PACKAGE_STATUS_EXPIRED,
    APPLICATION_PACKAGE_STATUS_CONSUMED,
}

# Canonical schema version for the package payload itself.
APPLICATION_PACKAGE_SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_nonempty_str(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    return normalized


@dataclass(frozen=True, slots=True)
class ApplicationPackageDocumentRef:
    """An immutable reference to a fixed-version candidate document."""

    document_id: str
    document_kind: str
    asset_id: str
    object_key: str
    mime_type: str
    file_name: str
    sha256_hex: str = ""
    document_version: int = 1

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageDocumentRef":
        return cls(
            document_id=_require_nonempty_str(payload.get("document_id"), "document_id"),
            document_kind=_require_nonempty_str(payload.get("document_kind"), "document_kind"),
            asset_id=_require_nonempty_str(payload.get("asset_id"), "asset_id"),
            object_key=_require_nonempty_str(payload.get("object_key"), "object_key"),
            mime_type=_require_nonempty_str(payload.get("mime_type"), "mime_type"),
            file_name=str(payload.get("file_name") or ""),
            sha256_hex=str(payload.get("sha256_hex") or ""),
            document_version=max(1, int(payload.get("document_version") or 1)),
        )


@dataclass(frozen=True, slots=True)
class ApplicationPackageAnswer:
    """One verified or scoped-preference answer in the package."""

    field_intent: str
    label: str
    proposed_value: str
    source: str  # "profile_verified" | "scoped_preference" | "ai_suggestion"
    sensitivity: str  # "standard" | "personal" | "legal" | "demographic"
    scope: str  # "application" | "country" | "role" | "company" | "global"
    confidence: float
    requires_review: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageAnswer":
        confidence = float(payload.get("confidence") or 0)
        return cls(
            field_intent=_require_nonempty_str(payload.get("field_intent"), "field_intent"),
            label=str(payload.get("label") or ""),
            proposed_value=str(payload.get("proposed_value") or payload.get("value") or ""),
            source=_require_nonempty_str(payload.get("source"), "source"),
            sensitivity=_require_nonempty_str(payload.get("sensitivity"), "sensitivity"),
            scope=_require_nonempty_str(payload.get("scope"), "scope"),
            confidence=max(0.0, min(1.0, confidence)),
            requires_review=bool(payload.get("requires_review")),
            reasons=[str(item) for item in payload.get("reasons") or []],
        )


@dataclass(frozen=True, slots=True)
class ApplicationPackageJob:
    """Job-identity section of the package."""

    job_id: str
    title: str
    company: str
    portal: str  # "greenhouse", "lever", or ""
    url: str = ""
    location: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageJob":
        return cls(
            job_id=_require_nonempty_str(payload.get("job_id"), "job_id"),
            title=str(payload.get("title") or ""),
            company=str(payload.get("company") or ""),
            portal=str(payload.get("portal") or ""),
            url=str(payload.get("url") or payload.get("apply_link") or ""),
            location=str(payload.get("location") or payload.get("location_raw") or ""),
        )


@dataclass(frozen=True, slots=True)
class ApplicationPackageWarnings:
    """Pre-flight warnings that do not block launch."""

    items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageWarnings":
        items = payload.get("items")
        return cls(items=[str(item) for item in items] if isinstance(items, list) else [])


@dataclass(frozen=True, slots=True)
class ApplicationPackagePolicy:
    """Package-scoped policy derived from preferences + provenance."""

    schema_version: int = APPLICATION_PACKAGE_SCHEMA_VERSION
    permit_sensitive_autofill: bool = False
    permit_demographic_autofill: bool = False
    require_legal_answer_confirmation: bool = True
    jurisdiction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackagePolicy":
        return cls(
            schema_version=int(payload.get("schema_version") or APPLICATION_PACKAGE_SCHEMA_VERSION),
            permit_sensitive_autofill=bool(payload.get("permit_sensitive_autofill")),
            permit_demographic_autofill=bool(payload.get("permit_demographic_autofill")),
            require_legal_answer_confirmation=bool(
                payload.get("require_legal_answer_confirmation", True)
            ),
            jurisdiction=str(payload.get("jurisdiction") or ""),
        )


@dataclass(slots=True)
class ApplicationPackage:
    """Immutable, versioned application package bound to one user/job.

    After creation, the payload (job, candidate, documents, answers, policy)
    MUST NOT be mutated. A new package version must be created for changes.
    """

    package_id: str
    user_id: str
    job_id: str
    version: int
    status: str
    schema_version: int

    # The launch envelope
    launch_tab_binding_id: str  # non-empty only when status=launched
    launch_tab_binding_expires_at: str

    # Immutable payload sections
    job: ApplicationPackageJob
    answers: list[ApplicationPackageAnswer]
    documents: list[ApplicationPackageDocumentRef]
    warnings: ApplicationPackageWarnings
    policy: ApplicationPackagePolicy

    created_at: str
    updated_at: str
    launched_at: str = ""
    bound_at: str = ""
    expired_at: str = ""
    consumed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "user_id": self.user_id,
            "job_id": self.job_id,
            "version": self.version,
            "status": self.status,
            "schema_version": self.schema_version,
            "launch_tab_binding_id": self.launch_tab_binding_id,
            "launch_tab_binding_expires_at": self.launch_tab_binding_expires_at,
            "job": self.job.to_dict(),
            "answers": [answer.to_dict() for answer in self.answers],
            "documents": [doc.to_dict() for doc in self.documents],
            "warnings": self.warnings.to_dict(),
            "policy": self.policy.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "launched_at": self.launched_at,
            "bound_at": self.bound_at,
            "expired_at": self.expired_at,
            "consumed_at": self.consumed_at,
        }

    def to_extension_payload(self) -> dict[str, Any]:
        """The subset sent to the extension after tab binding (no secrets)."""
        return {
            "packageId": self.package_id,
            "jobId": self.job_id,
            "version": self.version,
            "schemaVersion": self.schema_version,
            "job": {
                "jobId": self.job.job_id,
                "title": self.job.title,
                "company": self.job.company,
                "portal": self.job.portal,
                "location": self.job.location,
            },
            "answers": [
                {
                    "fieldIntent": answer.field_intent,
                    "label": answer.label,
                    "proposedValue": answer.proposed_value,
                    "source": answer.source,
                    "sensitivity": answer.sensitivity,
                    "scope": answer.scope,
                    "confidence": answer.confidence,
                    "requiresReview": answer.requires_review,
                    "reasons": list(answer.reasons),
                }
                for answer in self.answers
            ],
            "documents": [
                {
                    "documentId": doc.document_id,
                    "documentVersion": doc.document_version,
                    "documentKind": doc.document_kind,
                    "mimeType": doc.mime_type,
                    "fileName": doc.file_name,
                }
                for doc in self.documents
            ],
            "warnings": list(self.warnings.items),
            "policy": {
                "permitSensitiveAutofill": self.policy.permit_sensitive_autofill,
                "permitDemographicAutofill": self.policy.permit_demographic_autofill,
                "requireLegalAnswerConfirmation": self.policy.require_legal_answer_confirmation,
            },
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackage":
        raw_job = payload.get("job")
        raw_answers = payload.get("answers")
        raw_documents = payload.get("documents")
        raw_warnings = payload.get("warnings")
        raw_policy = payload.get("policy")

        return cls(
            package_id=_require_nonempty_str(payload.get("package_id"), "package_id"),
            user_id=_require_nonempty_str(payload.get("user_id"), "user_id"),
            job_id=_require_nonempty_str(payload.get("job_id"), "job_id"),
            version=int(payload.get("version") or 1),
            status=str(payload.get("status") or APPLICATION_PACKAGE_STATUS_CREATED),
            schema_version=int(
                payload.get("schema_version") or APPLICATION_PACKAGE_SCHEMA_VERSION
            ),
            launch_tab_binding_id=str(payload.get("launch_tab_binding_id") or ""),
            launch_tab_binding_expires_at=str(
                payload.get("launch_tab_binding_expires_at") or ""
            ),
            job=(
                ApplicationPackageJob.from_payload(raw_job)
                if isinstance(raw_job, Mapping)
                else ApplicationPackageJob(
                    job_id=payload.get("job_id") or "",
                    title="",
                    company="",
                    portal="",
                )
            ),
            answers=(
                [
                    ApplicationPackageAnswer.from_payload(item)
                    for item in raw_answers
                    if isinstance(item, Mapping)
                ]
                if isinstance(raw_answers, list)
                else []
            ),
            documents=(
                [
                    ApplicationPackageDocumentRef.from_payload(item)
                    for item in raw_documents
                    if isinstance(item, Mapping)
                ]
                if isinstance(raw_documents, list)
                else []
            ),
            warnings=(
                ApplicationPackageWarnings.from_payload(raw_warnings)
                if isinstance(raw_warnings, Mapping)
                else ApplicationPackageWarnings()
            ),
            policy=(
                ApplicationPackagePolicy.from_payload(raw_policy)
                if isinstance(raw_policy, Mapping)
                else ApplicationPackagePolicy()
            ),
            created_at=str(payload.get("created_at") or _utc_now_iso()),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or _utc_now_iso()),
            launched_at=str(payload.get("launched_at") or ""),
            bound_at=str(payload.get("bound_at") or ""),
            expired_at=str(payload.get("expired_at") or ""),
            consumed_at=str(payload.get("consumed_at") or ""),
        )


def new_application_package(
    *,
    user_id: str,
    job: ApplicationPackageJob,
    answers: list[ApplicationPackageAnswer],
    documents: list[ApplicationPackageDocumentRef],
    warnings: ApplicationPackageWarnings | None = None,
    policy: ApplicationPackagePolicy | None = None,
    version: int = 1,
    now: str | None = None,
) -> ApplicationPackage:
    now_iso = now or _utc_now_iso()
    return ApplicationPackage(
        package_id=f"{APPLICATION_PACKAGE_ID_PREFIX}{token_urlsafe(32)}",
        user_id=_require_nonempty_str(user_id, "user_id"),
        job_id=job.job_id,
        version=version,
        status=APPLICATION_PACKAGE_STATUS_CREATED,
        schema_version=APPLICATION_PACKAGE_SCHEMA_VERSION,
        launch_tab_binding_id="",
        launch_tab_binding_expires_at="",
        job=job,
        answers=list(answers),
        documents=list(documents),
        warnings=warnings or ApplicationPackageWarnings(),
        policy=policy or ApplicationPackagePolicy(),
        created_at=now_iso,
        updated_at=now_iso,
    )
