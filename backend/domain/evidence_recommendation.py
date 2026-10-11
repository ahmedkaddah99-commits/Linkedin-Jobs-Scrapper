"""Domain model for evidence recommendation against job requirements (CP-018).

Groups verified career-memory facts under job requirements and tracks
include/exclude decisions per evidence item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.domain.models import utc_now_iso


EVIDENCE_RECOMMENDATION_STATUS_PENDING = "pending"
EVIDENCE_RECOMMENDATION_STATUS_INCLUDED = "included"
EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED = "excluded"

EVIDENCE_RECOMMENDATION_STATUSES = {
    EVIDENCE_RECOMMENDATION_STATUS_PENDING,
    EVIDENCE_RECOMMENDATION_STATUS_INCLUDED,
    EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED,
}


@dataclass(slots=True)
class EvidenceMatch:
    """A pairing between a job requirement and a verified evidence fact."""

    match_id: str
    requirement_id: str
    fact_id: str
    evidence_text: str
    fact_type: str = ""
    certainty: str = ""
    source_file_name: str = ""
    source_asset_id: str = ""
    verification_state: str = "verified"
    match_reason: str = ""
    linked_experience: str = ""
    include_status: str = EVIDENCE_RECOMMENDATION_STATUS_PENDING
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "requirement_id": self.requirement_id,
            "fact_id": self.fact_id,
            "evidence_text": self.evidence_text,
            "fact_type": self.fact_type,
            "certainty": self.certainty,
            "source_file_name": self.source_file_name,
            "source_asset_id": self.source_asset_id,
            "verification_state": self.verification_state,
            "match_reason": self.match_reason,
            "linked_experience": self.linked_experience,
            "include_status": self.include_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceMatch":
        return cls(
            match_id=str(payload.get("match_id") or ""),
            requirement_id=str(payload.get("requirement_id") or ""),
            fact_id=str(payload.get("fact_id") or ""),
            evidence_text=str(payload.get("evidence_text") or ""),
            fact_type=str(payload.get("fact_type") or ""),
            certainty=str(payload.get("certainty") or ""),
            source_file_name=str(payload.get("source_file_name") or ""),
            source_asset_id=str(payload.get("source_asset_id") or ""),
            verification_state=str(payload.get("verification_state") or "verified"),
            match_reason=str(payload.get("match_reason") or ""),
            linked_experience=str(payload.get("linked_experience") or ""),
            include_status=str(payload.get("include_status") or EVIDENCE_RECOMMENDATION_STATUS_PENDING),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )


@dataclass(slots=True)
class RecommendationGroup:
    """A job requirement with its matched evidence items."""

    requirement_id: str
    requirement_label: str
    requirement_category: str = ""
    matches: list[EvidenceMatch] = field(default_factory=list)

    @property
    def included_matches(self) -> list[EvidenceMatch]:
        return [m for m in self.matches if m.include_status == EVIDENCE_RECOMMENDATION_STATUS_INCLUDED]

    @property
    def has_matches(self) -> bool:
        return len(self.matches) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "requirement_label": self.requirement_label,
            "requirement_category": self.requirement_category,
            "matches": [m.to_dict() for m in self.matches],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RecommendationGroup":
        return cls(
            requirement_id=str(payload.get("requirement_id") or ""),
            requirement_label=str(payload.get("requirement_label") or ""),
            requirement_category=str(payload.get("requirement_category") or ""),
            matches=[
                EvidenceMatch.from_dict(m)
                for m in (payload.get("matches") or [])
                if isinstance(m, dict)
            ],
        )


@dataclass(slots=True)
class EvidenceRecommendation:
    """Complete evidence recommendation result for a job."""

    recommendation_id: str
    job_id: str
    job_title: str = ""
    job_company: str = ""
    profile_id: str = ""
    groups: list[RecommendationGroup] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def total_matches(self) -> int:
        return sum(len(g.matches) for g in self.groups)

    @property
    def included_count(self) -> int:
        return sum(
            1 for g in self.groups for m in g.matches
            if m.include_status == EVIDENCE_RECOMMENDATION_STATUS_INCLUDED
        )

    @property
    def excluded_count(self) -> int:
        return sum(
            1 for g in self.groups for m in g.matches
            if m.include_status == EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "job_company": self.job_company,
            "profile_id": self.profile_id,
            "groups": [g.to_dict() for g in self.groups],
            "total_matches": self.total_matches,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRecommendation":
        return cls(
            recommendation_id=str(payload.get("recommendation_id") or ""),
            job_id=str(payload.get("job_id") or ""),
            job_title=str(payload.get("job_title") or ""),
            job_company=str(payload.get("job_company") or ""),
            profile_id=str(payload.get("profile_id") or ""),
            groups=[
                RecommendationGroup.from_dict(g)
                for g in (payload.get("groups") or [])
                if isinstance(g, dict)
            ],
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )


__all__ = [
    "EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED",
    "EVIDENCE_RECOMMENDATION_STATUS_INCLUDED",
    "EVIDENCE_RECOMMENDATION_STATUS_PENDING",
    "EVIDENCE_RECOMMENDATION_STATUSES",
    "EvidenceMatch",
    "EvidenceRecommendation",
    "RecommendationGroup",
]
