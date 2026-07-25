"""Domain model for candidate evidence extraction (CP-009).

Extracted from reviewed source texts, candidate evidence items represent
traceable claims about a candidate's career: achievements, responsibilities,
projects, metrics, skills, tools, leadership, stakeholders, challenges,
motivations, certifications, education, and domain experience.

Each evidence item carries full provenance back to its source document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping
from uuid import uuid4

from backend.domain.models import utc_now_iso


# ── Evidence types ──────────────────────────────────────────────────

EVIDENCE_TYPE_ACHIEVEMENT = "achievement"
EVIDENCE_TYPE_RESPONSIBILITY = "responsibility"
EVIDENCE_TYPE_PROJECT = "project"
EVIDENCE_TYPE_METRIC = "metric"
EVIDENCE_TYPE_SKILL = "skill"
EVIDENCE_TYPE_TOOL = "tool"
EVIDENCE_TYPE_LEADERSHIP = "leadership"
EVIDENCE_TYPE_STAKEHOLDER = "stakeholder"
EVIDENCE_TYPE_CHALLENGE = "challenge"
EVIDENCE_TYPE_MOTIVATION = "motivation"
EVIDENCE_TYPE_CERTIFICATION = "certification"
EVIDENCE_TYPE_EDUCATION = "education"
EVIDENCE_TYPE_DOMAIN_EXPERIENCE = "domain_experience"

EVIDENCE_TYPES = {
    EVIDENCE_TYPE_ACHIEVEMENT,
    EVIDENCE_TYPE_RESPONSIBILITY,
    EVIDENCE_TYPE_PROJECT,
    EVIDENCE_TYPE_METRIC,
    EVIDENCE_TYPE_SKILL,
    EVIDENCE_TYPE_TOOL,
    EVIDENCE_TYPE_LEADERSHIP,
    EVIDENCE_TYPE_STAKEHOLDER,
    EVIDENCE_TYPE_CHALLENGE,
    EVIDENCE_TYPE_MOTIVATION,
    EVIDENCE_TYPE_CERTIFICATION,
    EVIDENCE_TYPE_EDUCATION,
    EVIDENCE_TYPE_DOMAIN_EXPERIENCE,
}

# ── Evidence statuses ────────────────────────────────────────────────

EVIDENCE_STATUS_NEEDS_REVIEW = "needs_review"
EVIDENCE_STATUS_REVIEWED = "reviewed"
EVIDENCE_STATUS_CONFIRMED = "confirmed"
EVIDENCE_STATUS_REJECTED = "rejected"
EVIDENCE_STATUS_MERGED = "merged"
EVIDENCE_STATUS_CONFLICT = "conflict"

EVIDENCE_STATUSES = {
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REVIEWED,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_MERGED,
    EVIDENCE_STATUS_CONFLICT,
}

# ── Classification helpers ───────────────────────────────────────────

_NUMBER_PATTERN = re.compile(
    r"(?<!\w)(?:[$€£]\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*(?:hours?|days?|weeks?|months?|years?))?",
    re.I,
)

_OUTCOME_TERMS = (
    "improved", "reduced", "increased", "delivered", "achieved", "saved",
    "grew", "accelerated", "decreased", "boosted", "optimised",
    "optimized", "streamlined", "automated", "launched", "led",
    "transformed", "generated", "exceeded",
)

_TOOL_TERMS = (
    "python", "sql", "excel", "power bi", "tableau", "sap", "jira",
    "salesforce", "docker", "kubernetes", "aws", "azure", "gcp",
    "terraform", "jenkins", "git", "react", "angular", "vue",
    "node", "django", "flask", "spring", "spark", "kafka",
    "airflow", "snowflake", "databricks", "figma",
)

_STAKEHOLDER_TERMS = (
    "stakeholder", "customer", "client", "manager", "leadership",
    "team", "partner", "executive", "director", "vendor", "board",
)

_LEADERSHIP_TERMS = (
    "managed", "led", "mentored", "coached", "supervised", "directed",
    "guided", "headed", "oversaw", "coordinated", "facilitated",
)

_CHALLENGE_TERMS = (
    "challenge", "crisis", "issue", "obstacle", "setback",
    "constraint", "bottleneck", "risk",
)

_MOTIVATION_TERMS = (
    "passionate", "driven", "motivated", "enthusiastic", "committed",
    "dedicated", "eager", "purpose", "mission",
)

_CERTIFICATION_TERMS = (
    "certified", "certification", "certificate", "pmp", "csm", "cspo",
    "scrum master", "itil", "cissp", "comptia", "togaf",
    "six sigma", "prince2", "cfa", "cpa", "safe",
)

_EDUCATION_TERMS = (
    "bachelor", "master", "phd", "doctorate", "mba", "degree",
    "university", "college", "diploma", "b.s.", "m.s.", "b.a.",
)

_SKILL_INDICATORS = (
    "skilled in", "proficient in", "expertise in", "experienced in",
    "knowledge of", "strong", "familiar with", "competent",
)


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", str(text or "").strip().lower())
    return {token for token in cleaned.split() if len(token) > 1}


def classify_evidence_type(value: str) -> str:
    """Classify an evidence item into its most likely type."""
    lowered = value.lower()

    if _NUMBER_PATTERN.search(value):
        return EVIDENCE_TYPE_METRIC

    first_word = lowered.split()[0] if lowered.split() else ""
    if first_word in _OUTCOME_TERMS:
        return EVIDENCE_TYPE_ACHIEVEMENT

    if any(term in lowered for term in _CERTIFICATION_TERMS):
        return EVIDENCE_TYPE_CERTIFICATION

    if any(term in lowered for term in _EDUCATION_TERMS):
        return EVIDENCE_TYPE_EDUCATION

    if any(word in lowered.split() for word in _TOOL_TERMS):
        return EVIDENCE_TYPE_TOOL

    if any(term in lowered.split() for term in _LEADERSHIP_TERMS):
        return EVIDENCE_TYPE_LEADERSHIP

    if any(term in lowered for term in _STAKEHOLDER_TERMS):
        return EVIDENCE_TYPE_STAKEHOLDER

    if any(term in lowered for term in _CHALLENGE_TERMS):
        return EVIDENCE_TYPE_CHALLENGE

    if any(term in lowered for term in _MOTIVATION_TERMS):
        return EVIDENCE_TYPE_MOTIVATION

    if any(indicator in lowered for indicator in _SKILL_INDICATORS):
        return EVIDENCE_TYPE_SKILL

    if any(word in lowered for word in ("project", "initiative", "program", "campaign", "migration")):
        return EVIDENCE_TYPE_PROJECT

    if any(word in lowered for word in (
        "industry", "sector", "domain", "vertical", "market", "finance",
        "healthcare", "retail", "manufacturing", "logistics",
    )):
        return EVIDENCE_TYPE_DOMAIN_EXPERIENCE

    return EVIDENCE_TYPE_RESPONSIBILITY


def compute_content_hash(text: str) -> str:
    """Compute a stable hash for content-based comparison."""
    normalized = " ".join(sorted(_tokenize(text)))
    return sha256(normalized.encode("utf-8")).hexdigest()


# ── Certainty constants ──────────────────────────────────────────────

CERTAINTY_CONFIRMED = "confirmed"
CERTAINTY_ESTIMATED = "estimated"
CERTAINTY_UNCERTAIN = "uncertain"

CERTAINTIES = {CERTAINTY_CONFIRMED, CERTAINTY_ESTIMATED, CERTAINTY_UNCERTAIN}

# ── Evidence model ──────────────────────────────────────────────────

@dataclass(slots=True)
class CandidateEvidence:
    """A single traceable evidence item — the canonical evidence model (CP-032R).

    This is the single source of truth for every candidate claim across
    domain, API, UI, generation, and tests. Each item carries provenance
    back to its source document, lifecycle status, versioning, certainty,
    experience mapping, and optional generated output.
    """

    evidence_id: str
    profile_id: str = ""
    evidence_type: str = EVIDENCE_TYPE_RESPONSIBILITY
    text: str = ""
    source_asset: str = ""
    source_id: str = ""
    excerpt: str = ""
    location: str = ""
    confidence: float = 0.0
    inferred_employer: str = ""
    inferred_role: str = ""
    dates: list[str] = field(default_factory=list)
    status: str = EVIDENCE_STATUS_NEEDS_REVIEW
    duplicate_group_id: str = ""
    conflicting_with: list[str] = field(default_factory=list)
    content_hash: str = ""
    source_confidence: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Canonical fields added in CP-032R ──
    version: int = 1
    certainty: str = "estimated"
    experience_mapping: dict[str, str] = field(default_factory=dict)
    generated_output: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content_hash and self.text:
            self.content_hash = compute_content_hash(self.text)
        if not self.evidence_id:
            self.evidence_id = f"ev_{uuid4().hex[:16]}"
        if not self.created_at:
            self.created_at = utc_now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "profile_id": self.profile_id,
            "evidence_type": self.evidence_type,
            "text": self.text,
            "source_asset": self.source_asset,
            "source_id": self.source_id,
            "excerpt": self.excerpt,
            "location": self.location,
            "confidence": self.confidence,
            "inferred_employer": self.inferred_employer,
            "inferred_role": self.inferred_role,
            "dates": list(self.dates),
            "status": self.status,
            "duplicate_group_id": self.duplicate_group_id,
            "conflicting_with": list(self.conflicting_with),
            "content_hash": self.content_hash,
            "source_confidence": self.source_confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
            "version": self.version,
            "certainty": self.certainty,
            "experience_mapping": dict(self.experience_mapping),
            "generated_output": dict(self.generated_output),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateEvidence":
        return cls(
            evidence_id=str(payload.get("evidence_id") or ""),
            profile_id=str(payload.get("profile_id") or ""),
            evidence_type=str(payload.get("evidence_type") or EVIDENCE_TYPE_RESPONSIBILITY),
            text=str(payload.get("text") or ""),
            source_asset=str(payload.get("source_asset") or ""),
            source_id=str(payload.get("source_id") or ""),
            excerpt=str(payload.get("excerpt") or ""),
            location=str(payload.get("location") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            inferred_employer=str(payload.get("inferred_employer") or ""),
            inferred_role=str(payload.get("inferred_role") or ""),
            dates=[str(d) for d in (payload.get("dates") or [])],
            status=str(payload.get("status") or EVIDENCE_STATUS_NEEDS_REVIEW),
            duplicate_group_id=str(payload.get("duplicate_group_id") or ""),
            conflicting_with=[str(c) for c in (payload.get("conflicting_with") or [])],
            content_hash=str(payload.get("content_hash") or ""),
            source_confidence=float(payload.get("source_confidence") or 0.0),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            metadata=dict(payload.get("metadata") or {}),
            version=int(payload.get("version") or 1),
            certainty=str(payload.get("certainty") or "estimated"),
            experience_mapping=dict(payload.get("experience_mapping") or {}),
            generated_output=dict(payload.get("generated_output") or {}),
        )

    @classmethod
    def create(
        cls,
        *,
        profile_id: str = "",
        evidence_type: str = EVIDENCE_TYPE_RESPONSIBILITY,
        text: str,
        source_asset: str = "",
        source_id: str = "",
        excerpt: str = "",
        location: str = "",
        confidence: float = 0.0,
        inferred_employer: str = "",
        inferred_role: str = "",
        dates: list[str] | None = None,
        source_confidence: float = 0.0,
        metadata: Mapping[str, Any] | None = None,
        certainty: str = "estimated",
        experience_mapping: Mapping[str, str] | None = None,
        version: int = 1,
    ) -> "CandidateEvidence":
        now = utc_now_iso()
        return cls(
            evidence_id=f"ev_{uuid4().hex[:16]}",
            profile_id=str(profile_id).strip(),
            evidence_type=str(evidence_type or EVIDENCE_TYPE_RESPONSIBILITY).strip(),
            text=str(text).strip(),
            source_asset=str(source_asset).strip(),
            source_id=str(source_id).strip(),
            excerpt=str(excerpt).strip(),
            location=str(location).strip(),
            confidence=float(confidence or 0.0),
            inferred_employer=str(inferred_employer).strip(),
            inferred_role=str(inferred_role).strip(),
            dates=list(dates or []),
            source_confidence=float(source_confidence or 0.0),
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
            version=version,
            certainty=str(certainty or "estimated"),
            experience_mapping=dict(experience_mapping or {}),
        )

    @property
    def needs_review(self) -> bool:
        return self.status == EVIDENCE_STATUS_NEEDS_REVIEW

    @property
    def is_confirmed(self) -> bool:
        return self.status == EVIDENCE_STATUS_CONFIRMED

    @property
    def is_reviewed(self) -> bool:
        return self.status == EVIDENCE_STATUS_REVIEWED

    @property
    def is_rejected(self) -> bool:
        return self.status == EVIDENCE_STATUS_REJECTED

    @property
    def is_certainty_confirmed(self) -> bool:
        return self.certainty == "confirmed"

    @property
    def is_conflicting(self) -> bool:
        return self.status == EVIDENCE_STATUS_CONFLICT

    @property
    def is_merged(self) -> bool:
        return self.status == EVIDENCE_STATUS_MERGED

    def mark_reviewed(self) -> None:
        self.status = EVIDENCE_STATUS_REVIEWED
        self.updated_at = utc_now_iso()

    def confirm(self) -> None:
        self.status = EVIDENCE_STATUS_CONFIRMED
        self.certainty = "confirmed"
        self.updated_at = utc_now_iso()

    def reject(self) -> None:
        self.status = EVIDENCE_STATUS_REJECTED
        self.updated_at = utc_now_iso()

    def mark_conflict(self, conflicting_ids: list[str]) -> None:
        self.status = EVIDENCE_STATUS_CONFLICT
        self.conflicting_with = list(conflicting_ids)
        self.updated_at = utc_now_iso()

    def mark_merged(self, into_evidence_id: str) -> None:
        self.status = EVIDENCE_STATUS_MERGED
        self.duplicate_group_id = into_evidence_id
        self.updated_at = utc_now_iso()

    def assign_duplicate_group(self, group_id: str) -> None:
        self.duplicate_group_id = group_id
        self.updated_at = utc_now_iso()

    def new_version(self, *, text: str | None = None, **overrides: Any) -> "CandidateEvidence":
        """Create an immutable new version of this evidence item.

        Used when a user confirms/corrects evidence: the original
        version is preserved and a new version is created.
        """
        now = utc_now_iso()
        data = self.to_dict()
        data.pop("evidence_id", None)
        data["version"] = self.version + 1
        data["created_at"] = now
        data["updated_at"] = now
        if text is not None:
            data["text"] = text
            data["content_hash"] = compute_content_hash(text)
        data.update(overrides)
        return CandidateEvidence.from_dict(data)


__all__ = [
    "CERTAINTIES",
    "CERTAINTY_CONFIRMED",
    "CERTAINTY_ESTIMATED",
    "CERTAINTY_UNCERTAIN",
    "CandidateEvidence",
    "EVIDENCE_STATUS_CONFIRMED",
    "EVIDENCE_STATUS_CONFLICT",
    "EVIDENCE_STATUS_MERGED",
    "EVIDENCE_STATUS_NEEDS_REVIEW",
    "EVIDENCE_STATUS_REJECTED",
    "EVIDENCE_STATUS_REVIEWED",
    "EVIDENCE_STATUSES",
    "EVIDENCE_TYPE_ACHIEVEMENT",
    "EVIDENCE_TYPE_CERTIFICATION",
    "EVIDENCE_TYPE_CHALLENGE",
    "EVIDENCE_TYPE_DOMAIN_EXPERIENCE",
    "EVIDENCE_TYPE_EDUCATION",
    "EVIDENCE_TYPE_LEADERSHIP",
    "EVIDENCE_TYPE_METRIC",
    "EVIDENCE_TYPE_MOTIVATION",
    "EVIDENCE_TYPE_PROJECT",
    "EVIDENCE_TYPE_RESPONSIBILITY",
    "EVIDENCE_TYPE_SKILL",
    "EVIDENCE_TYPE_STAKEHOLDER",
    "EVIDENCE_TYPE_TOOL",
    "EVIDENCE_TYPES",
    "classify_evidence_type",
    "compute_content_hash",
]
