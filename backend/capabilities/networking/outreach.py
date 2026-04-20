from __future__ import annotations

import csv
import io
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
        company_candidates = [normalize_company_name(item) for item in referral_company_names(contact)]
        company_candidates = [item for item in company_candidates if item]
        if not company_candidates:
            continue
        if any(candidate == target or candidate in target or target in candidate for candidate in company_candidates):
            matches.append(contact)
    matches.sort(key=lambda item: (not item.can_refer, item.name.lower(), item.primary_company().lower()))
    return matches


def referral_company_names(contact: "ReferralContactRecord") -> list[str]:
    if hasattr(contact, "company_names"):
        names = [str(item).strip() for item in contact.company_names() if str(item).strip()]
        if names:
            return names
    raw_companies = getattr(contact, "companies", None) or []
    names = [
        str(item.get("company_name") or item.get("company") or "").strip()
        for item in raw_companies
        if isinstance(item, dict)
    ]
    names = [item for item in names if item]
    if names:
        return names
    fallback = str(getattr(contact, "company", "") or "").strip()
    return [fallback] if fallback else []


def parse_referral_contacts_csv(
    csv_text: str,
    *,
    source_kind: str = "linkedin_csv",
    import_batch_id: str = "",
) -> list["ReferralContactRecord"]:
    from backend.domain.models import ReferralContactRecord

    normalized_text = str(csv_text or "").lstrip("\ufeff").strip()
    if not normalized_text:
        return []
    reader = csv.DictReader(io.StringIO(normalized_text))
    parsed_contacts: list[ReferralContactRecord] = []
    for row in reader:
        normalized_row = {str(key or "").strip().lower(): value for key, value in (row or {}).items()}
        first_name = str(_csv_value(normalized_row, "first name", "firstname", "first_name")).strip()
        last_name = str(_csv_value(normalized_row, "last name", "lastname", "last_name")).strip()
        full_name = " ".join(part for part in (first_name, last_name) if part).strip()
        if not full_name:
            full_name = str(_csv_value(normalized_row, "name", "full name", "full_name")).strip()
        if not full_name:
            continue
        company_name = str(
            _csv_value(
                normalized_row,
                "company",
                "company name",
                "current company",
                "organization",
            )
        ).strip()
        role_title = str(_csv_value(normalized_row, "position", "title", "role", "headline")).strip()
        linkedin_url = str(
            _csv_value(
                normalized_row,
                "url",
                "profile url",
                "linkedin url",
                "linkedin_url",
            )
        ).strip()
        relationship_note = str(
            _csv_value(
                normalized_row,
                "notes",
                "connected on",
            )
        ).strip()
        metadata = {
            "import_source_row": {
                key: str(value).strip()
                for key, value in normalized_row.items()
                if str(value or "").strip()
            }
        }
        companies = (
            [{"company_name": company_name, "role_title": role_title, "can_refer": False}]
            if company_name
            else []
        )
        parsed_contacts.append(
            ReferralContactRecord.create(
                name=full_name,
                company=company_name,
                companies=companies,
                linkedin_url=linkedin_url,
                relationship_note=relationship_note,
                can_refer=False,
                source_kind=source_kind,
                import_batch_id=import_batch_id,
                import_ref=linkedin_url or full_name,
                metadata=metadata,
            )
        )
    return parsed_contacts


def merge_referral_contacts(
    existing_contacts: Iterable["ReferralContactRecord"],
    incoming_contacts: Iterable["ReferralContactRecord"],
) -> tuple[list["ReferralContactRecord"], dict[str, int]]:
    merged_contacts = [item for item in existing_contacts]
    index_by_identity: dict[str, int] = {}
    for idx, contact in enumerate(merged_contacts):
        index_by_identity[_referral_contact_identity(contact)] = idx
    created_count = 0
    updated_count = 0
    skipped_count = 0
    for incoming in incoming_contacts:
        identity = _referral_contact_identity(incoming)
        if not identity:
            skipped_count += 1
            continue
        existing_index = index_by_identity.get(identity)
        if existing_index is None:
            merged_contacts.append(incoming)
            index_by_identity[identity] = len(merged_contacts) - 1
            created_count += 1
            continue
        merged_contacts[existing_index] = _merge_referral_contact_record(merged_contacts[existing_index], incoming)
        updated_count += 1
    return merged_contacts, {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
    }


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
    company = str(job.company or contact.primary_company() or "your company").strip() or "your company"
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


def _csv_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(str(key or "").strip().lower())
        if str(value or "").strip():
            return str(value).strip()
    return ""


def _referral_contact_identity(contact: "ReferralContactRecord") -> str:
    linkedin_url = str(contact.linkedin_url or "").strip().lower()
    if linkedin_url:
        return f"linkedin:{linkedin_url.rstrip('/')}"
    normalized_name = _NON_ALNUM.sub("", str(contact.name or "").strip().lower())
    if normalized_name:
        return f"name:{normalized_name}"
    return ""


def _merge_referral_contact_record(
    existing: "ReferralContactRecord",
    incoming: "ReferralContactRecord",
) -> "ReferralContactRecord":
    merged_companies = _merge_company_entries(existing.companies, incoming.companies)
    merged_metadata = dict(existing.metadata or {})
    merged_metadata.update(dict(incoming.metadata or {}))
    return existing.__class__(
        contact_id=existing.contact_id,
        name=str(existing.name or incoming.name or "").strip(),
        company=next(
            (
                str(item.get("company_name") or "").strip()
                for item in merged_companies
                if str(item.get("company_name") or "").strip()
            ),
            str(existing.company or incoming.company or "").strip(),
        ),
        linkedin_url=str(existing.linkedin_url or incoming.linkedin_url or "").strip(),
        relationship_note=_merge_note(existing.relationship_note, incoming.relationship_note),
        can_refer=bool(existing.can_refer or incoming.can_refer or any(item.get("can_refer") for item in merged_companies)),
        companies=merged_companies,
        source_kind=str(existing.source_kind or incoming.source_kind or "manual").strip() or "manual",
        import_batch_id=str(incoming.import_batch_id or existing.import_batch_id or "").strip(),
        import_ref=str(incoming.import_ref or existing.import_ref or "").strip(),
        created_at=existing.created_at,
        updated_at=existing.updated_at,
        metadata=merged_metadata,
    )


def _merge_company_entries(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for entry in [*existing, *incoming]:
        if not isinstance(entry, dict):
            continue
        company_name = str(entry.get("company_name") or entry.get("company") or "").strip()
        if not company_name:
            continue
        key = normalize_company_name(company_name)
        normalized_entry = {
            "company_name": company_name,
            "company_domain": str(entry.get("company_domain") or "").strip(),
            "role_title": str(entry.get("role_title") or "").strip(),
            "employment_status": str(entry.get("employment_status") or "unknown").strip() or "unknown",
            "can_refer": bool(entry.get("can_refer") or False),
        }
        existing_index = seen.get(key)
        if existing_index is None:
            seen[key] = len(merged)
            merged.append(normalized_entry)
            continue
        current = merged[existing_index]
        if not current["company_domain"]:
            current["company_domain"] = normalized_entry["company_domain"]
        if not current["role_title"]:
            current["role_title"] = normalized_entry["role_title"]
        if current["employment_status"] == "unknown" and normalized_entry["employment_status"] != "unknown":
            current["employment_status"] = normalized_entry["employment_status"]
        current["can_refer"] = bool(current["can_refer"] or normalized_entry["can_refer"])
    return merged


def _merge_note(existing_note: str, incoming_note: str) -> str:
    existing_value = str(existing_note or "").strip()
    incoming_value = str(incoming_note or "").strip()
    if not existing_value:
        return incoming_value
    if not incoming_value or incoming_value.casefold() == existing_value.casefold():
        return existing_value
    return f"{existing_value}\n{incoming_value}"
