"""Generate evidence-backed personalized motivation letters."""

from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import Any
import requests
from .common import compact_whitespace, strip_json_fences
from .generation import normalize_output_language

MOTIVATION_LETTER_VERSION = "2026-07-22.evidence-backed-v1"
MINIMUM_MOTIVATION_EVIDENCE_POINTS = 2
MINIMUM_EXPERIENCE_EVIDENCE_POINTS = 2

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert career writing assistant who writes authentic, "
    "evidence-backed motivation letters. Ground every claim in verified "
    "experience and stated motivations. Never fabricate facts."
)

MOTIVATION_LETTER_LABELS = {
    "English": {
        "greeting": "Dear Hiring Team",
        "closing": "Sincerely",
        "section_why_role": "Why This Role",
        "section_why_company": "Why {company}",
        "section_fit": "My Fit for This Role",
        "section_closing": "Closing",
        "insufficient_warning": (
            "WARNING: Limited verified motivation evidence. "
            "Review and personalise before sending."
        ),
    },
    "German": {
        "greeting": "Sehr geehrtes Hiring-Team",
        "closing": "Mit freundlichen Gruessen",
        "section_why_role": "Warum diese Position",
        "section_why_company": "Warum {company}",
        "section_fit": "Meine Eignung fuer diese Rolle",
        "section_closing": "Abschluss",
        "insufficient_warning": (
            "WARNUNG: Begrenzte verifizierte Motivationsbelege. "
            "Vor dem Versand pruefen und personalisieren."
        ),
    },
}

@dataclass(slots=True)
class MotivationEvidence:
    evidence_id: str
    category: str
    statement: str
    source: str = ""
    confidence: str = "medium"

@dataclass(slots=True)
class ExperienceEvidence:
    experience_id: str
    role_title: str
    company: str
    period: str
    key_bullets: list[str] = field(default_factory=list)
    relevance_to_role: str = ""

@dataclass(slots=True)
class MotivationLetterInput:
    candidate_name: str
    job_title: str
    job_company: str
    job_description_text: str
    cv_text: str
    verified_experiences: list[ExperienceEvidence] = field(default_factory=list)
    verified_motivations: list[MotivationEvidence] = field(default_factory=list)
    candidate_email: str = ""
    company_context: str = ""
    role_requirements: list[str] = field(default_factory=list)
    extra_instructions: str = ""
    output_language: str = "English"

@dataclass(slots=True)
class MotivationLetterSection:
    heading: str
    body: str
    evidence_refs: list[str] = field(default_factory=list)
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(slots=True)
class MotivationLetterResult:
    job_id: str
    candidate_name: str
    letter_text: str
    sections: list[MotivationLetterSection] = field(default_factory=list)
    motivation_evidence_count: int = 0
    experience_evidence_count: int = 0
    evidence_insufficient: bool = False
    insufficient_warning: str = ""
    output_language: str = "English"
    error: str = ""
    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sections"] = [item.to_dict() for item in self.sections]
        return payload

def assess_evidence_sufficiency(
    verified_motivations: list[MotivationEvidence],
    verified_experiences: list[ExperienceEvidence],
) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    mc = len(verified_motivations)
    ec = len(verified_experiences)
    if mc < MINIMUM_MOTIVATION_EVIDENCE_POINTS:
        warnings.append(
            f"Only {mc} motivation point(s) available "
            f"(minimum: {MINIMUM_MOTIVATION_EVIDENCE_POINTS})."
        )
    if ec < MINIMUM_EXPERIENCE_EVIDENCE_POINTS:
        warnings.append(
            f"Only {ec} experience entry/entries available "
            f"(minimum: {MINIMUM_EXPERIENCE_EVIDENCE_POINTS})."
        )
    return mc > 0, warnings
