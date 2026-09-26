"""Application binding service for career profiles.

Connects a career profile to a specific job application, analyses
requirements and themes from the job description, and matches them
against verified work experience evidence.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from backend.domain.models import (
    APPLICATION_TYPE_TAILORED,
    APPLICATION_TYPES,
    MATCH_STATUS_MISSING,
    MATCH_STATUS_PARTIAL,
    MATCH_STATUS_STRONG,
    REQUIREMENT_CATEGORY_CERTIFICATION,
    REQUIREMENT_CATEGORY_DOMAIN,
    REQUIREMENT_CATEGORY_EDUCATION,
    REQUIREMENT_CATEGORY_EXPERIENCE,
    REQUIREMENT_CATEGORY_LANGUAGE,
    REQUIREMENT_CATEGORY_OTHER,
    REQUIREMENT_CATEGORY_SKILL,
    REQUIREMENT_CATEGORY_TOOL,
    WORK_EXPERIENCE_STATUS_ACTIVE,
    JobApplicationBinding,
    ProfileRequirementMatch,
    WorkExperienceRecord,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_APPLICATION_BINDINGS_KEY = "application_bindings"

STRONG_MATCH_THRESHOLD = 0.60
PARTIAL_MATCH_THRESHOLD = 0.30


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", _normalize(text))
    tokens: set[str] = set()
    for token in cleaned.split():
        if len(token) <= 1:
            continue
        for suffix in ("ment", "ing", "er", "ed"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                token = token[: -len(suffix)]
                break
        tokens.add(token)
    return tokens


def _fuzzy_score(text_a: str, text_b: str) -> float:
    """Measure how much of requirement ``text_a`` appears in evidence."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / len(tokens_a)


def _read_bindings(profile_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = profile_metadata.get(_APPLICATION_BINDINGS_KEY)
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _write_bindings(profile_metadata: dict[str, Any], bindings: list[dict[str, Any]]) -> None:
    profile_metadata[_APPLICATION_BINDINGS_KEY] = list(bindings)



# ---------------------------------------------------------------------------
# requirement extraction from job description
# ---------------------------------------------------------------------------

_SKILL_PATTERNS = (
    re.compile(r"\b(?:proficient|experience(?:d)?|skilled)\s+(?:in|with|using)\s+([\w\s+#.\-]+?)(?:\.|,|;|\band\b|\n|$)", re.IGNORECASE),
    re.compile(r"\b(?:knowledge|understanding)\s+of\s+([\w\s+#.\-]+?)(?:\.|,|;|\band\b|\n|$)", re.IGNORECASE),
    re.compile(r"\b(?:familiar|familiarity)\s+with\s+([\w\s+#.\-]+?)(?:\.|,|;|\band\b|\n|$)", re.IGNORECASE),
    re.compile(r"\b(?:hands-on|practical)\s+(?:experience|knowledge)\s+(?:in|with|of)\s+([\w\s+#.\-]+?)(?:\.|,|;|\band\b|\n|$)", re.IGNORECASE),
    re.compile(r"\b(?:strong|excellent|good|solid|deep|extensive)\s+(?:knowledge|understanding|skills?|background)\s+(?:in|of|with)\s+([\w\s+#.\-]+?)(?:\.|,|;|\band\b|\n|$)", re.IGNORECASE),
)

_TOOL_PATTERNS = (
    re.compile(r"\b(?:tool|platform|software|framework|technology|stack)(?:s)?\s+(?:such\s+as|like|including|:)\s+([\w\s+#.,\-]+?)(?:\.|;|\n|$)", re.IGNORECASE),
)

_EXPERIENCE_PATTERNS = (
    re.compile(r"(\d+[\+]?)\s*(?:\+\s*)?years?\s+(?:of\s+)?(?:relevant\s+)?(?:professional\s+)?(?:work\s+)?experience\s+(?:in|with|as\s+(?:an?\s+)?)([\w\s\-/#]+?)(?:\.|,|;|\n|$)", re.IGNORECASE),
    re.compile(r"(?:minimum|at\s+least|min\.?)\s+(\d+[\+]?)\s*(?:\+\s*)?years?\s+(?:of\s+)?experience\s+(?:in|with|as\s+(?:an?\s+)?)([\w\s\-/#]+?)(?:\.|,|;|\n|$)", re.IGNORECASE),
)

_EDUCATION_PATTERNS = (
    re.compile(r"\b(Bachelor(?:'s)?(?:\s+degree)?|B\.\s*[A-Z]+\.|Master(?:'s)?(?:\s+degree)?|M\.\s*[A-Z]+\.|PhD|Doctorate|MBA|Diploma)\s+(?:in|of)\s+([\w\s\-/#]+?)(?:\.|,|;|\n|$)", re.IGNORECASE),
    re.compile(r"\bdegree\s+(?:in|of)\s+([\w\s\-/#]+?)(?:\.|,|;|\n|$)", re.IGNORECASE),
)

_CERTIFICATION_PATTERNS = (
    re.compile(r"\b(?:certified|certification)\s+(?:in|as\s+(?:an?\s+)?)([\w\s\-/#]+?)(?:\.|,|;|\n|$)", re.IGNORECASE),
    re.compile(r"\b(?:PMP|AWS|Azure|GCP|CISSP|CCNA|SCRUM|SAFe|ITIL|PRINCE2|TOGAF|CPA|CFA)\b", re.IGNORECASE),
)

_LANGUAGE_PATTERNS = (
    re.compile(r"\b(?:fluent|proficient|business|native)\s+(?:in\s+)?(English|German|French|Spanish|Italian|Portuguese|Dutch|Mandarin|Japanese|Korean|Arabic|Russian|Chinese)(?:\s|\.|,|;|\n|$)", re.IGNORECASE),
    re.compile(r"\b(English|German|French|Spanish|Italian|Portuguese|Dutch|Mandarin|Japanese|Korean|Arabic|Russian|Chinese)\s+(?:language\s+)?(?:skills|proficiency|fluency)\b", re.IGNORECASE),
)


def _extract_skill_snippets(text: str) -> list[str]:
    skills: list[str] = []
    for pattern in _SKILL_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(1).strip()
            if len(snippet) > 3 and snippet not in skills:
                skills.append(snippet)
    return skills


def _extract_tool_snippets(text: str) -> list[str]:
    tools: list[str] = []
    for pattern in _TOOL_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(1).strip()
            if len(snippet) > 2 and snippet not in tools:
                tools.append(snippet)
    return tools


def _extract_experience_snippets(text: str) -> list[dict[str, str]]:
    experiences: list[dict[str, str]] = []
    for pattern in _EXPERIENCE_PATTERNS:
        for match in pattern.finditer(text):
            years = match.group(1).strip()
            domain = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else ""
            experiences.append({"years": years, "domain": domain})
    return experiences


def _extract_education_snippets(text: str) -> list[str]:
    education: list[str] = []
    for pattern in _EDUCATION_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0).strip()
            if snippet not in education:
                education.append(snippet)
    return education


def _extract_domain_terms(text: str) -> list[str]:
    domain_keywords = {
        "finance", "banking", "insurance", "healthcare", "medical",
        "pharmaceutical", "biotech", "manufacturing", "automotive",
        "aerospace", "retail", "e-commerce", "telecom", "energy",
        "oil", "gas", "utilities", "construction", "real estate",
        "logistics", "supply chain", "transportation", "education",
        "government", "public sector", "non-profit",
        "technology", "software", "hardware", "semiconductor",
        "media", "entertainment", "gaming", "hospitality",
        "agriculture", "food", "consulting",
        "legal", "law", "accounting", "audit", "tax",
        "marketing", "advertising", "design", "architecture",
        "cybersecurity", "cloud", "devops", "data science",
        "machine learning", "artificial intelligence", "ai",
        "blockchain", "iot", "embedded", "robotics",
        "sustainability", "renewable", "climate",
    }
    text_lower = _normalize(text)
    found: list[str] = []
    for domain in domain_keywords:
        if domain in text_lower and domain not in found:
            found.append(domain)
    return found


def _extract_certification_snippets(text: str) -> list[str]:
    certs: list[str] = []
    for pattern in _CERTIFICATION_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0).strip()
            if snippet not in certs:
                certs.append(snippet)
    return certs


def _extract_language_snippets(text: str) -> list[str]:
    langs: list[str] = []
    for pattern in _LANGUAGE_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0).strip()
            if snippet not in langs:
                langs.append(snippet)
    return langs



# ---------------------------------------------------------------------------
# theme extraction
# ---------------------------------------------------------------------------

_THEME_PATTERNS = (
    (re.compile(r"\b(?:team|collaborat(?:e|ion|ive)|cross-functional)\b", re.IGNORECASE), "teamwork"),
    (re.compile(r"\b(?:lead(?:er(?:ship)?|ing)?|manag(?:e|er|ement|ing)|mentor(?:ing)?|direct(?:or|ing)?)\b", re.IGNORECASE), "leadership"),
    (re.compile(r"\b(?:agile|scrum|kanban|sprint)\b", re.IGNORECASE), "agile"),
    (re.compile(r"\b(?:customer|client|user)[\s-](?:focus(?:ed)?|centric|facing|oriented)\b", re.IGNORECASE), "customer_focus"),
    (re.compile(r"\b(?:innovati(?:on|ve)|creative|disrupt(?:ive|ion)?|cutting[\s-]edge)\b", re.IGNORECASE), "innovation"),
    (re.compile(r"\b(?:data[\s-]driven|analytics|metrics|KPI|OKR|measur(?:e|able))\b", re.IGNORECASE), "data_driven"),
    (re.compile(r"\b(?:fast[\s-]paced|deadline|high[\s-]pressure|dynamic|adapt(?:able|ive)?)\b", re.IGNORECASE), "fast_paced"),
    (re.compile(r"\b(?:remote|hybrid|work[\s-]from[\s-]home|WFH|flexible\s+(?:work|schedule|hours?))\b", re.IGNORECASE), "flexible_work"),
    (re.compile(r"\b(?:start[\s-]?up|scale[\s-]?up|growth\s+(?:stage|phase|company))\b", re.IGNORECASE), "growth_company"),
    (re.compile(r"\b(?:enterprise|corporate|matrix(?:ed)?\s+organization|large[\s-]scale)\b", re.IGNORECASE), "enterprise"),
    (re.compile(r"\b(?:problem[\s-]solv(?:e|ing|er)|analytical|critical[\s-]thinking)\b", re.IGNORECASE), "problem_solving"),
    (re.compile(r"\b(?:communicati(?:on|ve)|present(?:ation|ing)?|interpersonal|stakeholder\s+management)\b", re.IGNORECASE), "communication"),
    (re.compile(r"\b(?:autonomous|self[\s-](?:starter|motivated|directed)|independent(?:ly)?|proactive)\b", re.IGNORECASE), "autonomy"),
    (re.compile(r"\b(?:detail[\s-]oriented|meticulous|thorough|quality[\s-]focused)\b", re.IGNORECASE), "attention_to_detail"),
    (re.compile(r"\b(?:diverse|diversity|inclusi(?:on|ve)|equity|belonging)\b", re.IGNORECASE), "diversity"),
)


def _extract_themes(text: str) -> list[str]:
    themes: list[str] = []
    text_lower = _normalize(text)
    for pattern, theme in _THEME_PATTERNS:
        if pattern.search(text_lower) and theme not in themes:
            themes.append(theme)
    return themes


# ---------------------------------------------------------------------------
# main requirement extraction
# ---------------------------------------------------------------------------

def analyse_job_requirements(
    job_description: str,
    *,
    job_title: str = "",
    company: str = "",
) -> dict[str, Any]:
    """Extract requirements and themes from a job description."""
    text = str(job_description or "")
    full_text = f"{job_title}\n{company}\n{text}".strip()

    skills = _extract_skill_snippets(full_text)
    tools = _extract_tool_snippets(full_text)
    exp_snippets = _extract_experience_snippets(full_text)
    education = _extract_education_snippets(full_text)
    certs = _extract_certification_snippets(full_text)
    langs = _extract_language_snippets(full_text)
    domains = _extract_domain_terms(full_text)
    themes = _extract_themes(full_text)

    requirements: list[dict[str, Any]] = []

    for idx, skill in enumerate(skills):
        requirements.append({
            "requirement_id": f"req_skill_{idx}",
            "requirement_text": skill,
            "requirement_category": REQUIREMENT_CATEGORY_SKILL,
        })

    for idx, tool in enumerate(tools):
        requirements.append({
            "requirement_id": f"req_tool_{idx}",
            "requirement_text": tool,
            "requirement_category": REQUIREMENT_CATEGORY_TOOL,
        })

    for idx, exp in enumerate(exp_snippets):
        dom = exp["domain"]
        yrs = exp["years"]
        requirements.append({
            "requirement_id": f"req_exp_{idx}",
            "requirement_text": f"{yrs} years experience in {dom}".strip(),
            "requirement_category": REQUIREMENT_CATEGORY_EXPERIENCE,
            "years_required": yrs,
            "domain": dom,
        })

    for idx, edu in enumerate(education):
        requirements.append({
            "requirement_id": f"req_edu_{idx}",
            "requirement_text": edu,
            "requirement_category": REQUIREMENT_CATEGORY_EDUCATION,
        })

    for idx, cert in enumerate(certs):
        requirements.append({
            "requirement_id": f"req_cert_{idx}",
            "requirement_text": cert,
            "requirement_category": REQUIREMENT_CATEGORY_CERTIFICATION,
        })

    for idx, lang in enumerate(langs):
        requirements.append({
            "requirement_id": f"req_lang_{idx}",
            "requirement_text": lang,
            "requirement_category": REQUIREMENT_CATEGORY_LANGUAGE,
        })

    for idx, domain in enumerate(domains):
        requirements.append({
            "requirement_id": f"req_domain_{idx}",
            "requirement_text": domain,
            "requirement_category": REQUIREMENT_CATEGORY_DOMAIN,
        })

    return {
        "requirements": requirements,
        "themes": themes,
    }



# ---------------------------------------------------------------------------
# evidence loading (verified, mapped)
# ---------------------------------------------------------------------------

def _load_verified_evidence(profile_metadata: dict[str, Any]) -> list[WorkExperienceRecord]:
    """Load only verified, mapped evidence from the profile."""
    raw = profile_metadata.get("work_experiences")
    if not isinstance(raw, list):
        return []
    records: list[WorkExperienceRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        record = WorkExperienceRecord.from_dict(item)
        if record.status == WORK_EXPERIENCE_STATUS_ACTIVE:
            records.append(record)
    return records




# ---------------------------------------------------------------------------
# requirement matching against evidence
# ---------------------------------------------------------------------------

def _build_evidence_text(experience: WorkExperienceRecord) -> str:
    """Build the searchable text for one verified work-experience record."""
    return " ".join(
        part.strip()
        for part in (
            experience.job_title,
            experience.employer,
            experience.location,
            experience.employment_type,
            experience.description,
        )
        if str(part or "").strip()
    )


def _match_requirement(
    requirement: dict[str, Any],
    evidence_records: list[WorkExperienceRecord],
) -> ProfileRequirementMatch:
    """Match a single requirement against verified evidence."""
    req_text = str(requirement.get("requirement_text") or "")
    req_category = str(requirement.get("requirement_category") or REQUIREMENT_CATEGORY_OTHER)
    req_id = str(requirement.get("requirement_id") or "")

    best_score = 0.0
    best_evidence_ids: list[str] = []
    best_snippets: list[dict[str, str]] = []

    for exp in evidence_records:
        evidence_text = _build_evidence_text(exp)
        title_employer = f"{exp.job_title} {exp.employer}"
        title_score = _fuzzy_score(req_text, title_employer)
        evidence_score = _fuzzy_score(req_text, evidence_text)
        # A requirement fully supported in either the role identity or the
        # complete evidence text is a full match; do not dilute an exact
        # description match merely because it is absent from the title.
        combined_score = max(title_score, evidence_score)

        if combined_score >= PARTIAL_MATCH_THRESHOLD and combined_score > best_score:
            best_score = combined_score
            best_evidence_ids = [exp.experience_id]
            snippet_text = str(exp.description or "")[:200]
            best_snippets = [{
                "experience_id": exp.experience_id,
                "title": exp.job_title,
                "employer": exp.employer,
                "snippet": snippet_text,
            }]

    if best_score >= STRONG_MATCH_THRESHOLD:
        match_status = MATCH_STATUS_STRONG
        match_detail = f"Strong evidence match (score {best_score:.0%})"
    elif best_score >= PARTIAL_MATCH_THRESHOLD:
        match_status = MATCH_STATUS_PARTIAL
        match_detail = f"Partial evidence match (score {best_score:.0%})"
    else:
        match_status = MATCH_STATUS_MISSING
        match_detail = "No matching evidence found in profile"
        best_evidence_ids = []
        best_snippets = []

    return ProfileRequirementMatch(
        requirement_id=req_id,
        requirement_text=req_text,
        requirement_category=req_category,
        match_status=match_status,
        matched_evidence_ids=best_evidence_ids,
        match_score=best_score,
        match_detail=match_detail,
        evidence_snippets=best_snippets,
    )


def _compute_coverage_score(matches: list[ProfileRequirementMatch]) -> float:
    if not matches:
        return 0.0
    strong = sum(1 for m in matches if m.match_status == MATCH_STATUS_STRONG)
    partial = sum(1 for m in matches if m.match_status == MATCH_STATUS_PARTIAL)
    return round((strong * 1.0 + partial * 0.5) / len(matches), 4)


def _build_match_summary(matches: list[ProfileRequirementMatch]) -> str:
    strong = sum(1 for m in matches if m.match_status == MATCH_STATUS_STRONG)
    partial = sum(1 for m in matches if m.match_status == MATCH_STATUS_PARTIAL)
    missing = sum(1 for m in matches if m.match_status == MATCH_STATUS_MISSING)
    parts: list[str] = []
    if strong:
        parts.append(f"{strong} requirement(s) strongly matched.")
    if partial:
        parts.append(f"{partial} requirement(s) partially matched.")
    if missing:
        parts.append(f"{missing} requirement(s) have no matching evidence.")
    if not parts:
        parts.append("No requirements extracted from job description.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CRUD: application bindings stored in profile metadata
# ---------------------------------------------------------------------------

def list_application_bindings(profile) -> list[JobApplicationBinding]:
    """Return all application bindings for a career profile."""
    metadata = dict(profile.metadata or {})
    raw = _read_bindings(metadata)
    bindings = [JobApplicationBinding.from_dict(item) for item in raw]
    bindings.sort(key=lambda b: b.created_at or "", reverse=True)
    return bindings


def get_application_binding(profile, binding_id: str) -> JobApplicationBinding | None:
    """Get a single application binding by id."""
    metadata = dict(profile.metadata or {})
    raw = _read_bindings(metadata)
    for item in raw:
        if str(item.get("binding_id") or "") == binding_id:
            return JobApplicationBinding.from_dict(item)
    return None


def create_application_binding(
    profile,
    *,
    job_id: str,
    run_id: str = "",
    job_title: str = "",
    company: str = "",
    location: str = "",
    target_role: str = "",
    application_type: str = APPLICATION_TYPE_TAILORED,
    description_text: str = "",
) -> JobApplicationBinding:
    """Create a new application binding with requirement analysis and evidence matching."""
    metadata = dict(profile.metadata or {})
    raw = _read_bindings(metadata)

    normalized_app_type = str(application_type or APPLICATION_TYPE_TAILORED).strip()
    if normalized_app_type not in APPLICATION_TYPES:
        normalized_app_type = APPLICATION_TYPE_TAILORED

    # Step 1: analyse job requirements
    analysis = analyse_job_requirements(
        description_text,
        job_title=job_title,
        company=company,
    )
    extracted_requirements = list(analysis["requirements"])
    extracted_themes = list(analysis["themes"])

    # Step 2: load verified evidence
    evidence = _load_verified_evidence(metadata)

    # Step 3: match requirements against evidence
    matches: list[ProfileRequirementMatch] = []
    for req in extracted_requirements:
        match = _match_requirement(req, evidence)
        matches.append(match)

    # Step 4: compute coverage and summary
    coverage_score = _compute_coverage_score(matches)
    match_summary = _build_match_summary(matches)

    binding = JobApplicationBinding.create(
        profile_id=profile.profile_id,
        job_id=job_id,
        run_id=run_id,
        job_title=job_title,
        company=company,
        location=location,
        target_role=target_role,
        application_type=normalized_app_type,
        description_text=description_text,
    )
    binding.extracted_requirements = extracted_requirements
    binding.extracted_themes = extracted_themes
    binding.requirement_matches = matches
    binding.match_summary = match_summary
    binding.coverage_score = coverage_score

    raw.append(binding.to_dict())
    _write_bindings(metadata, raw)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()

    return binding


def delete_application_binding(profile, binding_id: str) -> None:
    """Delete an application binding from the profile."""
    metadata = dict(profile.metadata or {})
    raw = _read_bindings(metadata)
    updated = [item for item in raw if str(item.get("binding_id") or "") != binding_id]
    if len(updated) == len(raw):
        raise KeyError(f"Application binding '{binding_id}' not found.")
    _write_bindings(metadata, updated)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
