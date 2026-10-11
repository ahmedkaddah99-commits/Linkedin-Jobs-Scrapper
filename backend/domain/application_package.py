from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any, ClassVar, Mapping

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


class ApplicationPackageMutationError(ValueError):
    """Raised when approved package content is changed in place."""


@dataclass(frozen=True, slots=True)
class ResolvedApplicationValue:
    value: str = ""
    source: str = "unresolved"
    provenance: str = ""
    requires_review: bool = False


def resolve_approved_value(
    job_specific: Mapping[str, Any] | None,
    selected_cv: Mapping[str, Any] | None,
    career_memory: Mapping[str, Any] | None,
    *,
    sensitive: bool = False,
) -> ResolvedApplicationValue:
    """Resolve only explicit approved/confirmed values in fixed precedence."""
    for source_name, candidate in (
        ("job_specific", job_specific),
        ("selected_cv", selected_cv),
        ("career_memory", career_memory),
    ):
        if not isinstance(candidate, Mapping):
            continue
        value = str(candidate.get("value") or candidate.get("text") or "")
        allowed = bool(candidate.get("approved")) if source_name != "career_memory" else bool(candidate.get("confirmed"))
        if not value or not allowed:
            continue
        return ResolvedApplicationValue(
            value=value,
            source=source_name,
            provenance=str(candidate.get("provenance") or candidate.get("source") or ""),
            requires_review=sensitive,
        )
    return ResolvedApplicationValue(requires_review=sensitive)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_nonempty_str(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    return normalized


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    import hashlib
    return hashlib.sha256(encoded).hexdigest()


def _without_nested_hashes(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _without_nested_hashes(item) for key, item in value.items() if key != "content_hash"}
    if isinstance(value, list):
        return [_without_nested_hashes(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ApplicationPackageCandidate:
    """Approved personal/contact facts; empty values are unresolved."""

    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    source: str = ""
    approved: bool = False
    provenance: str = ""
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageCandidate":
        value = cls(
            first_name=str(payload.get("first_name") or ""),
            last_name=str(payload.get("last_name") or ""),
            full_name=str(payload.get("full_name") or ""),
            email=str(payload.get("email") or ""),
            phone=str(payload.get("phone") or ""),
            source=str(payload.get("source") or ""),
            approved=bool(payload.get("approved")),
            provenance=str(payload.get("provenance") or ""),
            content_hash=str(payload.get("content_hash") or ""),
        )
        expected = _canonical_hash({key: getattr(value, key) for key in (
            "first_name", "last_name", "full_name", "email", "phone", "source", "approved", "provenance")})
        if value.content_hash and value.content_hash != expected:
            raise ValueError("Candidate content hash does not match.")
        return value if value.content_hash else replace(value, content_hash=expected)


@dataclass(frozen=True, slots=True)
class ApplicationPackageBullet:
    text: str
    approved_text: str
    bullet_id: str = ""
    source_experience_id: str = ""
    provenance_id: str = ""
    approved: bool = True
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageBullet":
        approved_text = str(payload.get("approved_text") if "approved_text" in payload else payload.get("text") or "")
        text = str(payload.get("text") if "text" in payload else approved_text)
        value = cls(
            bullet_id=str(payload.get("bullet_id") or ""),
            text=text,
            approved_text=approved_text,
            source_experience_id=str(payload.get("source_experience_id") or ""),
            provenance_id=str(payload.get("provenance_id") or ""),
            approved=bool(payload.get("approved", bool(payload.get("bullet_id")))),
            content_hash=str(payload.get("content_hash") or ""),
        )
        if value.approved and value.text != value.approved_text:
            raise ValueError("Approved bullet text cannot be mutated.")
        expected = _canonical_hash({key: getattr(value, key) for key in (
            "bullet_id", "text", "approved_text", "source_experience_id", "provenance_id", "approved")})
        if value.content_hash and value.content_hash != expected:
            raise ValueError("Bullet content hash does not match.")
        return value if value.content_hash else replace(value, content_hash=expected)


@dataclass(frozen=True, slots=True)
class ApplicationPackageExperience:
    role_title: str
    company: str
    source_experience_id: str = ""
    period: str = ""
    location: str = ""
    bullets: list[ApplicationPackageBullet] = field(default_factory=list)
    selected_cv_version: dict[str, Any] = field(default_factory=dict)
    generation_provenance: dict[str, Any] = field(default_factory=dict)
    provenance_confidence: str = "full"
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["bullets"] = [bullet.to_dict() for bullet in self.bullets]
        return value

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageExperience":
        bullets = []
        for item in payload.get("bullets") or []:
            if isinstance(item, Mapping):
                bullets.append(ApplicationPackageBullet.from_payload(item))
            elif isinstance(item, str) and item:
                bullets.append(ApplicationPackageBullet(text=item, approved_text=item, approved=False))
        value = cls(
            role_title=str(payload.get("role_title") or ""),
            company=str(payload.get("company") or ""),
            source_experience_id=str(payload.get("source_experience_id") or ""),
            period=str(payload.get("period") or ""),
            location=str(payload.get("location") or ""),
            bullets=bullets,
            selected_cv_version=dict(payload.get("selected_cv_version") or {}),
            generation_provenance=dict(payload.get("generation_provenance") or {}),
            provenance_confidence=str(payload.get("provenance_confidence") or ("full" if payload.get("source_experience_id") else "reduced")),
            content_hash=str(payload.get("content_hash") or ""),
        )
        expected = _canonical_hash({key: value.to_dict()[key] for key in (
            "source_experience_id", "role_title", "company", "period", "location", "bullets",
            "selected_cv_version", "generation_provenance", "provenance_confidence")})
        if value.content_hash and value.content_hash != expected:
            raise ValueError("Experience content hash does not match.")
        return value if value.content_hash else replace(value, content_hash=expected)


@dataclass(frozen=True, slots=True)
class ApplicationPackageEducation:
    institution: str
    degree: str
    period: str = ""
    provenance: str = ""
    confirmed: bool = True
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageEducation":
        value = cls(
            institution=str(payload.get("institution") or ""),
            degree=str(payload.get("degree") or payload.get("degree_title") or ""),
            period=str(payload.get("period") or ""),
            provenance=str(payload.get("provenance") or ""),
            confirmed=bool(payload.get("confirmed", True)),
            content_hash=str(payload.get("content_hash") or ""),
        )
        expected = _canonical_hash({key: getattr(value, key) for key in ("institution", "degree", "period", "provenance", "confirmed")})
        if value.content_hash and value.content_hash != expected:
            raise ValueError("Education content hash does not match.")
        return value if value.content_hash else replace(value, content_hash=expected)


@dataclass(frozen=True, slots=True)
class ApplicationPackageFact:
    value: str
    provenance: str = ""
    confirmed: bool = True
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageFact":
        value = cls(
            value=_require_nonempty_str(payload.get("value"), "value"),
            provenance=str(payload.get("provenance") or ""),
            confirmed=bool(payload.get("confirmed", True)),
            content_hash=str(payload.get("content_hash") or ""),
        )
        expected = _canonical_hash({key: getattr(value, key) for key in ("value", "provenance", "confirmed")})
        if value.content_hash and value.content_hash != expected:
            raise ValueError("Fact content hash does not match.")
        return value if value.content_hash else replace(value, content_hash=expected)


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
    approved: bool = False
    provenance: str = ""
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationPackageAnswer":
        confidence = float(payload.get("confidence") or 0)
        value = cls(
            field_intent=_require_nonempty_str(payload.get("field_intent"), "field_intent"),
            label=str(payload.get("label") or ""),
            proposed_value=str(payload.get("proposed_value") or payload.get("value") or ""),
            source=_require_nonempty_str(payload.get("source"), "source"),
            sensitivity=_require_nonempty_str(payload.get("sensitivity"), "sensitivity"),
            scope=_require_nonempty_str(payload.get("scope"), "scope"),
            confidence=max(0.0, min(1.0, confidence)),
            requires_review=bool(payload.get("requires_review")),
            reasons=[str(item) for item in payload.get("reasons") or []],
            approved=bool(payload.get("approved")),
            provenance=str(payload.get("provenance") or ""),
            content_hash=str(payload.get("content_hash") or ""),
        )
        if value.sensitivity in {"personal", "demographic", "legal"} and value.approved:
            value = replace(value, requires_review=True)
        expected = _canonical_hash({key: getattr(value, key) for key in (
            "field_intent", "label", "proposed_value", "source", "sensitivity", "scope",
            "confidence", "requires_review", "reasons", "approved", "provenance")})
        if value.content_hash and value.content_hash != expected:
            raise ValueError("Answer content hash does not match.")
        return value if value.content_hash else replace(value, content_hash=expected)


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
    candidate: ApplicationPackageCandidate = field(default_factory=ApplicationPackageCandidate)
    experiences: list[ApplicationPackageExperience] = field(default_factory=list)
    education: list[ApplicationPackageEducation] = field(default_factory=list)
    skills: list[ApplicationPackageFact] = field(default_factory=list)
    languages: list[ApplicationPackageFact] = field(default_factory=list)
    standard_answers: list[ApplicationPackageAnswer] = field(default_factory=list)
    content_hashes: dict[str, str] = field(default_factory=dict)

    launched_at: str = ""
    bound_at: str = ""
    expired_at: str = ""
    consumed_at: str = ""
    approved_at: str = ""
    approved_content_hash: str = ""

    _IMMUTABLE_CONTENT_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "job", "answers", "documents", "candidate", "experiences", "education",
        "skills", "languages", "standard_answers", "content_hashes",
    })

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._IMMUTABLE_CONTENT_FIELDS and hasattr(self, "approved_at") and (
            getattr(self, "approved_at", "") or
            getattr(self, "approved_content_hash", "") or
            getattr(self, "status", "") in {APPLICATION_PACKAGE_STATUS_BOUND, APPLICATION_PACKAGE_STATUS_CONSUMED}
        ):
            raise ApplicationPackageMutationError(
                "Approved application package content requires a new package version."
            )
        if name == "approved_content_hash":
            current = getattr(self, "approved_content_hash", "")
            if current and value != current:
                raise ApplicationPackageMutationError(
                    "Approved application package content requires a new package version."
                )
        object.__setattr__(self, name, value)

    def content_sections(self) -> dict[str, Any]:
        return _without_nested_hashes({
            "candidate": self.candidate.to_dict(),
            "experiences": [item.to_dict() for item in self.experiences],
            "education": [item.to_dict() for item in self.education],
            "skills": [item.to_dict() for item in self.skills],
            "languages": [item.to_dict() for item in self.languages],
            "answers": [item.to_dict() for item in self.answers],
            "standard_answers": [item.to_dict() for item in self.standard_answers],
            "documents": [item.to_dict() for item in self.documents],
        })

    def compute_content_hashes(self) -> dict[str, str]:
        return {section: _canonical_hash(value) for section, value in self.content_sections().items()}

    def refresh_content_hashes(self) -> None:
        self.content_hashes = self.compute_content_hashes()

    def assert_content_hashes(self) -> None:
        expected = self.compute_content_hashes()
        if self.approved_content_hash and self.approved_content_hash != _canonical_hash(self.content_sections()):
            raise ApplicationPackageMutationError(
                "Approved application package content requires a new package version."
            )
        if self.content_hashes and self.content_hashes != expected:
            raise ValueError("Application package content hashes do not match.")

    def mark_approved(self, approved_at: str | None = None) -> None:
        self.assert_content_hashes()
        self.approved_at = approved_at or _utc_now_iso()
        self.approved_content_hash = _canonical_hash(self.content_sections())

    def replace_content(self, **changes: Any) -> None:
        if self.approved_at or self.approved_content_hash or self.status in {APPLICATION_PACKAGE_STATUS_BOUND, APPLICATION_PACKAGE_STATUS_CONSUMED}:
            raise ApplicationPackageMutationError("Approved application package content requires a new package version.")
        allowed = {"candidate", "experiences", "education", "skills", "languages", "answers", "standard_answers", "documents"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported application package content fields: {sorted(unknown)}")
        for key, value in changes.items():
            setattr(self, key, value)
        self.refresh_content_hashes()

    def new_version(self, **changes: Any) -> "ApplicationPackage":
        payload = self.to_dict()
        for key, value in changes.items():
            if hasattr(value, "to_dict"):
                payload[key] = value.to_dict()
            elif isinstance(value, list):
                payload[key] = [item.to_dict() if hasattr(item, "to_dict") else item for item in value]
            else:
                payload[key] = value
        payload.update({"version": self.version + 1, "status": APPLICATION_PACKAGE_STATUS_CREATED,
                        "approved_at": "", "approved_content_hash": "", "bound_at": "",
                        "launch_tab_binding_id": "", "launch_tab_binding_expires_at": "",
                        "content_hashes": {}})
        return ApplicationPackage.from_payload(payload)

    def to_dict(self) -> dict[str, Any]:
        self.assert_content_hashes()
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
            "candidate": self.candidate.to_dict(),
            "experiences": [item.to_dict() for item in self.experiences],
            "education": [item.to_dict() for item in self.education],
            "skills": [item.to_dict() for item in self.skills],
            "languages": [item.to_dict() for item in self.languages],
            "standard_answers": [item.to_dict() for item in self.standard_answers],
            "content_hashes": dict(self.content_hashes),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "launched_at": self.launched_at,
            "bound_at": self.bound_at,
            "expired_at": self.expired_at,
            "consumed_at": self.consumed_at,
            "approved_at": self.approved_at,
            "approved_content_hash": self.approved_content_hash,
        }

    def to_extension_payload(self) -> dict[str, Any]:
        """The subset sent to the extension after tab binding (no secrets)."""
        self.assert_content_hashes()
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
                "url": self.job.url,
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
            "candidate": {
                "firstName": self.candidate.first_name,
                "lastName": self.candidate.last_name,
                "fullName": self.candidate.full_name,
                "email": self.candidate.email,
                "phone": self.candidate.phone,
                "source": self.candidate.source,
                "approved": self.candidate.approved,
                "provenance": self.candidate.provenance,
                "contentHash": self.candidate.content_hash,
            },
            "experiences": [
                {
                    "sourceExperienceId": item.source_experience_id,
                    "roleTitle": item.role_title,
                    "company": item.company,
                    "period": item.period,
                    "location": item.location,
                    "bullets": [
                        {
                            "bulletId": bullet.bullet_id,
                            "approvedText": bullet.approved_text,
                            "sourceExperienceId": bullet.source_experience_id,
                            "provenanceId": bullet.provenance_id,
                            "contentHash": bullet.content_hash,
                        }
                        for bullet in item.bullets
                    ],
                    "contentHash": item.content_hash,
                }
                for item in self.experiences
            ],
            "education": [
                {
                    "institution": item.institution,
                    "degree": item.degree,
                    "period": item.period,
                    "contentHash": item.content_hash,
                }
                for item in self.education
            ],
            "skills": [{"value": item.value, "contentHash": item.content_hash} for item in self.skills],
            "languages": [{"value": item.value, "contentHash": item.content_hash} for item in self.languages],
            "standardAnswers": [
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
                for answer in self.standard_answers
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

        package = cls(
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
            candidate=(
                ApplicationPackageCandidate.from_payload(raw_candidate)
                if isinstance((raw_candidate := payload.get("candidate")), Mapping)
                else ApplicationPackageCandidate()
            ),
            experiences=[
                ApplicationPackageExperience.from_payload(item)
                for item in payload.get("experiences") or []
                if isinstance(item, Mapping)
            ],
            education=[
                ApplicationPackageEducation.from_payload(item)
                for item in payload.get("education") or []
                if isinstance(item, Mapping)
            ],
            skills=[
                ApplicationPackageFact.from_payload(item)
                for item in payload.get("skills") or []
                if isinstance(item, Mapping)
            ],
            languages=[
                ApplicationPackageFact.from_payload(item)
                for item in payload.get("languages") or []
                if isinstance(item, Mapping)
            ],
            standard_answers=[
                ApplicationPackageAnswer.from_payload(item)
                for item in payload.get("standard_answers") or []
                if isinstance(item, Mapping)
            ],
            content_hashes={str(key): str(value) for key, value in dict(payload.get("content_hashes") or {}).items()},
            created_at=str(payload.get("created_at") or _utc_now_iso()),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or _utc_now_iso()),
            launched_at=str(payload.get("launched_at") or ""),
            bound_at=str(payload.get("bound_at") or ""),
            expired_at=str(payload.get("expired_at") or ""),
            consumed_at=str(payload.get("consumed_at") or ""),
            approved_at=str(payload.get("approved_at") or ""),
            approved_content_hash=str(payload.get("approved_content_hash") or ""),
        )
        expected_hashes = package.compute_content_hashes()
        if package.content_hashes and package.content_hashes != expected_hashes:
            raise ValueError("Application package content hashes do not match.")
        if not package.content_hashes:
            package.content_hashes = expected_hashes
        if package.approved_content_hash and package.approved_content_hash != _canonical_hash(package.content_sections()):
            raise ValueError("Approved application package content has changed.")
        return package


def new_application_package(
    *,
    user_id: str,
    job: ApplicationPackageJob,
    answers: list[ApplicationPackageAnswer],
    documents: list[ApplicationPackageDocumentRef],
    warnings: ApplicationPackageWarnings | None = None,
    policy: ApplicationPackagePolicy | None = None,
    candidate: ApplicationPackageCandidate | None = None,
    experiences: list[ApplicationPackageExperience] | None = None,
    education: list[ApplicationPackageEducation] | None = None,
    skills: list[ApplicationPackageFact] | None = None,
    languages: list[ApplicationPackageFact] | None = None,
    standard_answers: list[ApplicationPackageAnswer] | None = None,
    version: int = 1,
    now: str | None = None,
) -> ApplicationPackage:
    now_iso = now or _utc_now_iso()
    package = ApplicationPackage(
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
        candidate=candidate or ApplicationPackageCandidate(),
        experiences=list(experiences or []),
        education=list(education or []),
        skills=list(skills or []),
        languages=list(languages or []),
        standard_answers=list(standard_answers or []),
    )
    package.refresh_content_hashes()
    return package
