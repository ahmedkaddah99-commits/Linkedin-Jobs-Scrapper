"""Evidence extraction from reviewed source texts (CP-009).

Extracts candidate evidence items from reviewed and confirmed source texts.
Each evidence item carries provenance: source asset, excerpt/location,
confidence, inferred employer/role, and dates.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.domain.candidate_evidence import CandidateEvidence, classify_evidence_type
from backend.domain.models import utc_now_iso

LOGGER = logging.getLogger(__name__)

_MIN_SENTENCE_LENGTH = 15
_MAX_SENTENCE_LENGTH = 320
_SENTENCE_SPLIT = re.compile(r"(?:\r?\n)+|(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    candidates = _SENTENCE_SPLIT.split(str(text or ""))
    seen: set[str] = set()
    cleaned: list[str] = []
    for candidate in candidates:
        sentence = re.sub(r"^\s*[-*•]\s*", "", candidate).strip()
        key = sentence.lower()
        if _MIN_SENTENCE_LENGTH <= len(sentence) <= _MAX_SENTENCE_LENGTH and key not in seen:
            seen.add(key)
            cleaned.append(sentence)
    return cleaned


def _infer_employer(text: str, headings: list[str]) -> str:
    for heading in headings:
        parts = re.split(r"\s*[|@–—-]+\s*", heading)
        for part in parts:
            part = part.strip()
            role_words = ("engineer", "manager", "analyst", "developer", "consultant",
                          "designer", "architect", "scientist", "director", "lead",
                          "head", "officer", "specialist")
            if part and not any(rw in part.lower() for rw in role_words):
                if 2 < len(part) < 80:
                    return part
    return ""


def _infer_role(text: str) -> str:
    pattern = re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,5})\s*(?:Engineer|Manager|Analyst|"
        r"Developer|Consultant|Designer|Architect|Scientist|Director|Lead|"
        r"Head|Officer|Specialist|Coordinator|Assistant|Associate)", re.I)
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def extract_evidence_from_source(
    *,
    profile_id: str,
    source_id: str,
    text: str,
    source_asset: str,
    confidence: float,
    headings: list[str] | None = None,
    location: str = "",
    dates: list[str] | None = None,
) -> list[CandidateEvidence]:
    """Extract candidate evidence items from a single reviewed source text.

    Each item is marked as needs_review initially.
    """
    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    headings_list = list(headings or [])
    dates_list = list(dates or [])
    inferred_employer = _infer_employer(text, headings_list)
    inferred_role = _infer_role(text)

    evidence_items: list[CandidateEvidence] = []
    for idx, sentence in enumerate(sentences):
        ev_type = classify_evidence_type(sentence)
        loc = location or f"sentence {idx + 1}"
        evidence = CandidateEvidence.create(
            profile_id=profile_id,
            evidence_type=ev_type,
            text=sentence,
            source_asset=source_asset,
            source_id=source_id,
            excerpt=sentence,
            location=loc,
            confidence=confidence,
            inferred_employer=inferred_employer,
            inferred_role=inferred_role,
            dates=dates_list,
            source_confidence=confidence,
        )
        evidence_items.append(evidence)

    LOGGER.info(
        "Extracted %d evidence items from source %s (asset=%s)",
        len(evidence_items), source_id, source_asset,
    )
    return evidence_items


def extract_evidence_from_verified_sources(
    profile_id: str,
    verified_texts: list[dict[str, Any]],
) -> list[CandidateEvidence]:
    """Extract evidence from a batch of verified source texts.

    verified_texts format matches source_text_review.get_verified_texts().
    Returns a list of CandidateEvidence items across all sources.
    """
    all_evidence: list[CandidateEvidence] = []
    for vt in verified_texts:
        source_id = str(vt.get("source_id") or "")
        source_asset = str(vt.get("file_name") or source_id)
        text = str(vt.get("text") or "")
        confidence = float(vt.get("confidence") or 0.0)
        items = extract_evidence_from_source(
            profile_id=profile_id,
            source_id=source_id,
            text=text,
            source_asset=source_asset,
            confidence=confidence,
        )
        all_evidence.extend(items)

    LOGGER.info(
        "Extracted %d total evidence from %d verified sources for profile %s",
        len(all_evidence), len(verified_texts), profile_id,
    )
    return all_evidence


def build_evidence_summary(
    evidence_items: list[CandidateEvidence],
) -> dict[str, Any]:
    """Build a summary of extracted evidence items."""
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for ev in evidence_items:
        by_type[ev.evidence_type] = by_type.get(ev.evidence_type, 0) + 1
        by_status[ev.status] = by_status.get(ev.status, 0) + 1
    return {
        "total_evidence": len(evidence_items),
        "by_type": by_type,
        "by_status": by_status,
        "needs_review_count": by_status.get("needs_review", 0),
        "evidence": [ev.to_dict() for ev in evidence_items],
    }

