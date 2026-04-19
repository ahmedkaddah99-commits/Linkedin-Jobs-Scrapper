from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

from backend.domain.models import JobRecord

if TYPE_CHECKING:
    from backend.domain.models import ReferralContactRecord


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")
_MANAGER_PATTERNS = [
    re.compile(r"report(?:ing)?\s+to\s+(?P<name>[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,2})", re.IGNORECASE),
    re.compile(
        r"(?:hiring manager|manager|director|head of)\s*[:\-]\s*(?P<name>[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,2})",
        re.IGNORECASE,
    ),
]
_TITLE_PATTERNS = [
    re.compile(r"\b(?P<title>Head of [A-Z][A-Za-z&/ ]+)\b"),
    re.compile(r"\b(?P<title>Director of [A-Z][A-Za-z&/ ]+)\b"),
    re.compile(r"\b(?P<title>Hiring Manager)\b", re.IGNORECASE),
    re.compile(r"\b(?P<title>Team Lead)\b", re.IGNORECASE),
]


@dataclass(slots=True)
class HiringManagerMatch:
    name: str = ""
    title: str = ""
    confidence: str = "low"
    source: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "title": self.title,
            "confidence": self.confidence,
            "source": self.source,
        }


def normalize_company_name(value: str) -> str:
    normalized = _NON_ALNUM.sub(" ", str(value or "").strip().lower())
    return _WHITESPACE.sub(" ", normalized).strip()


def find_referral_contacts_for_company(
    contacts: Iterable["ReferralContactRecord"],
    company_name: str,
) -> list["ReferralContactRecord"]:
    target = normalize_company_name(company_name)
    if not target:
        return []
    matches: list["ReferralContactRecord"] = []
    for contact in contacts:
        candidate = normalize_company_name(contact.company)
        if not candidate:
            continue
        if candidate == target or candidate in target or target in candidate:
            matches.append(contact)
    matches.sort(key=lambda item: (not item.can_refer, item.name.lower(), item.company.lower()))
    return matches


def guess_hiring_manager_from_job(job: JobRecord) -> HiringManagerMatch:
    extra_fields = dict(job.extra_fields or {})
    direct_name = str(extra_fields.get("hiring_manager_name") or "").strip()
    direct_title = str(extra_fields.get("hiring_manager_title") or "").strip()
    if direct_name or direct_title:
        return HiringManagerMatch(
            name=direct_name,
            title=direct_title or "Hiring Manager",
            confidence="high" if direct_name else "medium",
            source="job_metadata",
        )

    description = str(job.description_text or extra_fields.get("description") or "").strip()
    for pattern in _MANAGER_PATTERNS:
        match = pattern.search(description)
        if match:
            name = str(match.groupdict().get("name") or "").strip()
            title = _guess_manager_title(description)
            return HiringManagerMatch(
                name=name,
                title=title or "Hiring Manager",
                confidence="medium" if name else "low",
                source="job_description",
            )

    title = _guess_manager_title(description)
    return HiringManagerMatch(
        name="",
        title=title or "Hiring Manager",
        confidence="low",
        source="fallback",
    )


def build_referral_outreach_draft(
    *,
    profile: dict[str, Any],
    job: JobRecord,
    contact: "ReferralContactRecord",
) -> dict[str, Any]:
    candidate_name = str(profile.get("name") or "").strip() or "I"
    role_title = str(job.title or "this role").strip() or "this role"
    company = str(job.company or contact.company or "your company").strip() or "your company"
    contact_name = str(contact.name or "there").strip() or "there"
    summary = _profile_summary(profile)
    ask = (
        "If you think it makes sense, would you feel comfortable referring me?"
        if contact.can_refer
        else "If you think it makes sense, I would really appreciate any guidance on the application."
    )
    message = (
        f"Hi {contact_name}, I hope you're doing well. I’m applying for the {role_title} role at {company}, "
        f"and it stood out because it aligns closely with my background in {summary}. "
        f"I’m tailoring my application around the role requirements and thought to reach out given our connection. "
        f"{ask}"
    )
    return {
        "contact": contact.to_dict(),
        "job": _job_summary(job),
        "message": message,
        "subject": f"Quick favor about the {role_title} role at {company}",
    }


def build_hiring_manager_outreach_draft(
    *,
    profile: dict[str, Any],
    job: JobRecord,
    hiring_manager: HiringManagerMatch,
) -> dict[str, Any]:
    role_title = str(job.title or "this role").strip() or "this role"
    company = str(job.company or "your team").strip() or "your team"
    greeting_target = hiring_manager.name or "Hiring Manager"
    summary = _profile_summary(profile)
    message = (
        f"Hi {greeting_target}, I just applied for the {role_title} role at {company}. "
        f"My background in {summary} is closely aligned with the problems described in the posting, "
        f"and I wanted to introduce myself directly. "
        "If it helps, I’d be glad to share a short summary of my experience or answer any questions."
    )
    return {
        "hiring_manager": hiring_manager.to_dict(),
        "job": _job_summary(job),
        "message": message,
        "subject": f"Applied for {role_title} at {company}",
    }


def _guess_manager_title(description_text: str) -> str:
    for pattern in _TITLE_PATTERNS:
        match = pattern.search(description_text or "")
        if match:
            return str(match.groupdict().get("title") or match.group(0) or "").strip()
    return ""


def _profile_summary(profile: dict[str, Any]) -> str:
    summary = str(profile.get("summary") or "").strip()
    if summary:
        sentence = summary.split(".")[0].strip()
        return sentence.rstrip(".")
    recent_experience = profile.get("recent_experience") or []
    if isinstance(recent_experience, list) and recent_experience:
        first = recent_experience[0] if isinstance(recent_experience[0], dict) else {}
        role_title = str(first.get("role") or "").strip()
        company = str(first.get("company") or "").strip()
        if role_title and company:
            return f"{role_title} work at {company}"
        if role_title:
            return role_title
    competencies = [
        str(item).strip()
        for item in (profile.get("competencies") or [])
        if str(item).strip()
    ]
    if competencies:
        return ", ".join(competencies[:3])
    role_title = str(profile.get("role_title") or "").strip()
    if role_title:
        return role_title
    return "relevant work in this area"


def _job_summary(job: JobRecord) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "title": job.title,
        "company": job.company,
        "apply_link": job.apply_link or job.link or job.source_url,
        "source_type": job.source_type,
    }
