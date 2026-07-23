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


def build_evidence_from_profile(
    profile: dict[str, Any],
) -> tuple[list[MotivationEvidence], list[ExperienceEvidence]]:
    """Extract motivation and experience evidence from a career profile dict."""
    motivations: list[MotivationEvidence] = []
    experiences: list[ExperienceEvidence] = []

    # Extract career goal as motivation
    if profile.get("career_goal"):
        motivations.append(
            MotivationEvidence(
                evidence_id="profile_career_goal",
                category="career_goal",
                statement=str(profile["career_goal"]),
                confidence="high",
            )
        )

    # Extract motivation reason
    if profile.get("motivation"):
        motivations.append(
            MotivationEvidence(
                evidence_id="profile_motivation",
                category="personal_motivation",
                statement=str(profile["motivation"]),
                confidence="high",
            )
        )
    elif profile.get("summary"):
        # Fall back to summary with low confidence
        motivations.append(
            MotivationEvidence(
                evidence_id="profile_summary",
                category="personal_motivation",
                statement=str(profile["summary"]),
                confidence="low",
            )
        )

    # Extract recent experience
    for i, exp in enumerate(profile.get("recent_experience", [])):
        bullets = exp.get("bullets", [])
        if not bullets:
            bullets = []
        experiences.append(
            ExperienceEvidence(
                experience_id=f"profile_exp_{i}",
                role_title=str(exp.get("title") or exp.get("role") or ""),
                company=str(exp.get("company", "")),
                period=str(exp.get("period", "")),
                key_bullets=[str(b) for b in bullets[:4]],
            )
        )

    return motivations, experiences


def build_motivation_prompt(input_data: MotivationLetterInput) -> str:
    """Build a prompt string for an LLM to generate a motivation letter."""
    parts: list[str] = [
        "Write a personalized motivation letter.",
        f"Candidate: {input_data.candidate_name}",
        f"Job Title: {input_data.job_title}",
        f"Company: {input_data.job_company}",
        f"Job Description: {input_data.job_description_text}",
        f"CV: {input_data.cv_text}",
    ]

    if input_data.company_context:
        parts.append(f"Company Context: {input_data.company_context}")

    if input_data.role_requirements:
        parts.append("Role Requirements:")
        for req in input_data.role_requirements:
            parts.append(f"- {req}")

    if input_data.verified_motivations:
        parts.append("Verified Motivations:")
        for m in input_data.verified_motivations:
            parts.append(f"- [{m.evidence_id}] {m.statement}")

    if input_data.verified_experiences:
        parts.append("Verified Experience:")
        for e in input_data.verified_experiences:
            parts.append(
                f"- [{e.experience_id}] {e.role_title} at {e.company}: "
                f"{', '.join(e.key_bullets)}"
            )

    if input_data.output_language:
        parts.append(f"Output language: {input_data.output_language}")

    return "\n".join(parts)


def generate_motivation_letter_for_job(
    deepseek_api_key: str,
    deepseek_model: str,
    job: dict[str, Any],
    cv_text: str,
    candidate_name: str,
    verified_motivations: list[MotivationEvidence] | None = None,
    verified_experiences: list[ExperienceEvidence] | None = None,
    company_context: str = "",
    role_requirements: list[str] | None = None,
    output_language: str = "English",
) -> MotivationLetterResult:
    """Generate a motivation letter for a specific job via DeepSeek API."""
    if not deepseek_api_key:
        return MotivationLetterResult(
            job_id=str(job.get("job_id", "")),
            candidate_name=candidate_name,
            letter_text="",
            evidence_insufficient=True,
            insufficient_warning="Missing DeepSeek API key.",
        )

    input_data = MotivationLetterInput(
        candidate_name=candidate_name,
        job_title=str(job.get("title", "")),
        job_company=str(job.get("company", "")),
        job_description_text=str(job.get("full_description", "")),
        cv_text=cv_text,
        verified_motivations=verified_motivations or [],
        verified_experiences=verified_experiences or [],
        company_context=company_context,
        role_requirements=role_requirements or [],
        output_language=output_language,
    )

    prompt = build_motivation_prompt(input_data)

    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": deepseek_model,
                "messages": [
                    {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        letter_text = data["choices"][0]["message"]["content"]
    except Exception:
        return MotivationLetterResult(
            job_id=str(job.get("job_id", "")),
            candidate_name=candidate_name,
            letter_text="",
            evidence_insufficient=True,
            insufficient_warning="Failed to generate letter via DeepSeek API.",
        )

    return MotivationLetterResult(
        job_id=str(job.get("job_id", "")),
        candidate_name=candidate_name,
        letter_text=letter_text,
        evidence_insufficient=False,
        motivation_evidence_count=len(verified_motivations or []),
        experience_evidence_count=len(verified_experiences or []),
    )
