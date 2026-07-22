"""Evidence recommendation service (CP-018).

Matches verified career-memory facts against job requirements, grouping
results by requirement and filtering out unverified or rejected evidence.
"""

from __future__ import annotations

import logging
import re
from hashlib import sha256
from typing import Any, Iterable, Mapping
from uuid import uuid4

from backend.career_memory.service import _active_facts, _store
from backend.capabilities.source_text_review import list_reviews
from backend.domain.evidence_recommendation import (
    EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED,
    EVIDENCE_RECOMMENDATION_STATUS_INCLUDED,
    EVIDENCE_RECOMMENDATION_STATUS_PENDING,
    EvidenceMatch,
    EvidenceRecommendation,
    RecommendationGroup,
)
from backend.domain.models import utc_now_iso
from backend.domain.source_text_review import SOURCE_REVIEW_STATUS_CONFIRMED

LOGGER = logging.getLogger(__name__)

# In-memory store keyed by recommendation_id
_recommendations: dict[str, EvidenceRecommendation] = {}


def _verified_source_ids(profile_id: str) -> set[str]:
    reviews = list_reviews(profile_id)
    return {r.source_id for r in reviews if r.status == SOURCE_REVIEW_STATUS_CONFIRMED}


def _verified_facts(user) -> list[dict[str, Any]]:
    stored = _store(user)
    facts = _active_facts(stored)
    return [f for f in facts if str(f.get("certainty") or "").strip() == "confirmed"]


def _fact_source_ids(fact: Mapping[str, Any]) -> set[str]:
    return {str(s.get("asset_id") or "") for s in (fact.get("sources") or [])}


def _fact_linked_experience(fact: Mapping[str, Any]) -> str:
    subject = dict(fact.get("subject") or {})
    parts = []
    if str(subject.get("company") or "").strip():
        parts.append(str(subject["company"]).strip())
    if str(subject.get("role") or "").strip():
        parts.append(str(subject["role"]).strip())
    if str(subject.get("project") or "").strip():
        parts.append(str(subject["project"]).strip())
    return " / ".join(parts) if parts else ""


def _tokenize(value: str) -> set[str]:
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9+#-]*", str(value or "").casefold())
    return {t for t in tokens if len(t) > 2}


def _match_score(requirement_text: str, evidence_text: str) -> tuple[int, str]:
    req_tokens = _tokenize(requirement_text)
    ev_tokens = _tokenize(evidence_text)
    if not req_tokens or not ev_tokens:
        return 0, ""
    overlap = req_tokens & ev_tokens
    score = len(overlap)
    if score == 0:
        return 0, ""
    matched_words = sorted(overlap)[:5]
    reason = f"Keyword match on: {', '.join(matched_words)}"
    if len(overlap) > 5:
        reason += f" (and {len(overlap) - 5} more)"
    return score, reason


def generate_recommendations(
    user,
    *,
    job_id: str,
    job_title: str = "",
    job_company: str = "",
    profile_id: str = "",
    requirements: list[dict[str, Any]] | None = None,
    candidate_asset_map: Mapping[str, Mapping[str, Any]] | None = None,
) -> EvidenceRecommendation:
    """Match verified facts against job requirements and return grouped recommendations.

    Only facts whose source asset has been verified (confirmed review) AND whose
    certainty is "confirmed" are eligible. Unverified or rejected evidence is
    never recommended.
    """
    now = utc_now_iso()
    reqs = requirements or []
    asset_map = dict(candidate_asset_map or {})

    verified_sources = _verified_source_ids(profile_id) if profile_id else set()
    confirmed_facts = _verified_facts(user)

    fact_lookup: dict[str, dict[str, Any]] = {}
    for fact in confirmed_facts:
        fid = str(fact.get("fact_id") or "")
        if fid:
            fact_lookup[fid] = dict(fact)

    groups: list[RecommendationGroup] = []

    for req in reqs:
        req_id = str(req.get("id") or req.get("requirement_id") or f"req_{uuid4().hex[:12]}")
        req_label = str(req.get("label") or req.get("description") or req_id)
        req_category = str(req.get("category") or "")
        matches: list[EvidenceMatch] = []

        for fact in confirmed_facts:
            fact_id = str(fact.get("fact_id") or "")
            if not fact_id:
                continue
            fact_sources = _fact_source_ids(fact)
            if verified_sources and not fact_sources.issubset(verified_sources):
                continue
            evidence_text = str(fact.get("value") or "")
            if not evidence_text.strip():
                continue
            score, reason = _match_score(req_label, evidence_text)
            if score == 0:
                continue
            source_asset_id = next(iter(fact_sources), "")
            source_file_name = ""
            if source_asset_id and source_asset_id in asset_map:
                source_file_name = str(
                    asset_map[source_asset_id].get("display_name")
                    or asset_map[source_asset_id].get("file_name")
                    or ""
                )
            match_id = f"match_{sha256(f'{req_id}:{fact_id}'.encode()).hexdigest()[:16]}"
            matches.append(
                EvidenceMatch(
                    match_id=match_id,
                    requirement_id=req_id,
                    fact_id=fact_id,
                    evidence_text=evidence_text,
                    fact_type=str(fact.get("type") or ""),
                    certainty=str(fact.get("certainty") or "confirmed"),
                    source_file_name=source_file_name,
                    source_asset_id=source_asset_id,
                    verification_state="verified",
                    match_reason=reason,
                    linked_experience=_fact_linked_experience(fact),
                    include_status=EVIDENCE_RECOMMENDATION_STATUS_PENDING,
                    created_at=now,
                    updated_at=now,
                )
            )

        groups.append(
            RecommendationGroup(
                requirement_id=req_id,
                requirement_label=req_label,
                requirement_category=req_category,
                matches=matches,
            )
        )

    rec_id = f"rec_{sha256(f'{job_id}:{profile_id}'.encode()).hexdigest()[:16]}"
    recommendation = EvidenceRecommendation(
        recommendation_id=rec_id,
        job_id=job_id,
        job_title=job_title,
        job_company=job_company,
        profile_id=profile_id,
        groups=groups,
        created_at=now,
        updated_at=now,
    )
    _recommendations[rec_id] = recommendation
    return recommendation


def get_recommendation(recommendation_id: str) -> EvidenceRecommendation | None:
    """Retrieve a previously generated recommendation by ID."""
    return _recommendations.get(str(recommendation_id or ""))


def set_match_status(
    recommendation_id: str,
    match_id: str,
    status: str,
) -> EvidenceRecommendation | None:
    """Update include/exclude status of a single evidence match."""
    recommendation = _recommendations.get(str(recommendation_id or ""))
    if recommendation is None:
        return None
    valid = {
        EVIDENCE_RECOMMENDATION_STATUS_INCLUDED,
        EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED,
        EVIDENCE_RECOMMENDATION_STATUS_PENDING,
    }
    if status not in valid:
        raise ValueError(f"Invalid status: {status}")
    now = utc_now_iso()
    matched = False
    for group in recommendation.groups:
        for match in group.matches:
            if match.match_id == match_id:
                match.include_status = status
                match.updated_at = now
                matched = True
                break
    if not matched:
        return None
    recommendation.updated_at = now
    return recommendation
