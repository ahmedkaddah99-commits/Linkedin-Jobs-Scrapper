"""Generate evidence-backed personalized motivation letters."""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any
import requests
from .common import compact_whitespace, strip_json_fences
from .generation import normalize_output_language

MOTIVATION_LETTER_VERSION = "2026-07-26.evidence-backed-sections-v2"
MINIMUM_MOTIVATION_EVIDENCE_POINTS = 2
MINIMUM_EXPERIENCE_EVIDENCE_POINTS = 2

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert career writing assistant who writes authentic, "
    "evidence-backed motivation letters. Ground every claim in verified "
    "experience and stated motivations. Never fabricate facts."
)

ANTI_COPY_SYSTEM_PROMPT = (
    "You are an expert career writing assistant who writes authentic, "
    "evidence-backed motivation letters.\n\n"
    "CRITICAL RULES:\n"
    "- NEVER copy text verbatim from the CV or the job description. "
    "Rewrite everything in your own words.\n"
    "- NEVER fabricate facts, skills, achievements, or experience not "
    "present in the provided verified evidence.\n"
    "- Every claim about the candidate MUST reference at least one "
    "verified evidence ID (e.g., [ev_motivation_X] or [ev_exp_X]).\n"
    "- Be concise, professional, and honest.\n"
    "- Do NOT include placeholders, templates, or generic filler text. "
    "If evidence is insufficient for a claim, reduce the scope of that "
    "section rather than inventing content."
)

MOTIVATION_GENERATION_PROMPT = (
    "Write a structured motivation letter in {output_language}.\n\n"
    "Candidate: {candidate_name}\n"
    "Job Title: {job_title}\n"
    "Company: {job_company}\n\n"
    "=== VERIFIED MOTIVATION EVIDENCE (only use these) ===\n"
    "{motivation_evidence}\n\n"
    "=== VERIFIED EXPERIENCE EVIDENCE (only use these) ===\n"
    "{experience_evidence}\n\n"
    "=== ROLE CONTEXT ===\n"
    "{role_context}\n\n"
    "=== COMPANY CONTEXT ===\n"
    "{company_context}\n\n"
    "=== SELECTED REQUIREMENTS ===\n"
    "{requirements}\n\n"
    "OUTPUT FORMAT: Return ONLY valid JSON (no markdown fences, no extra text):\n"
    "{{\n"
    '  "letter_text": "full letter as a single string with greeting and closing",\n'
    '  "sections": [\n'
    "    {{\n"
    '      "heading": "section heading",\n'
    '      "body": "section body text",\n'
    '      "evidence_refs": ["ev_id_1", "ev_id_2"]\n'
    "    }}\n"
    "  ]\n"
    "}}\n\n"
    "RULES:\n"
    "1. Include at least these sections: greeting, why_role, why_company, fit, closing.\n"
    "2. Each section body MUST reference evidence IDs like [ev_motivation_X] or [ev_exp_X].\n"
    "3. The evidence_refs list per section MUST match the evidence IDs used in that section.\n"
    "4. NEVER copy CV text or job description text verbatim. Paraphrase everything.\n"
    "5. NEVER invent facts not supported by the provided verified evidence.\n"
    "6. If evidence is insufficient for a section, keep it brief instead of fabricating.\n"
    "7. Write in {output_language}. Use the appropriate greeting and closing for that language."
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
        "insufficient_warning_motivation": (
            "WARNING: Limited verified motivation evidence. "
            "Review and personalise before sending."
        ),
        "insufficient_warning_experience": (
            "WARNING: Limited verified experience evidence. "
            "Review and personalise before sending."
        ),
        "insufficient_warning_general": (
            "WARNING: Insufficient verified evidence for a strong motivation letter. "
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
        "insufficient_warning_motivation": (
            "WARNUNG: Begrenzte verifizierte Motivationsbelege. "
            "Vor dem Versand pruefen und personalisieren."
        ),
        "insufficient_warning_experience": (
            "WARNUNG: Begrenzte verifizierte Erfahrungsbelege. "
            "Vor dem Versand pruefen und personalisieren."
        ),
        "insufficient_warning_general": (
            "WARNUNG: Unzureichende verifizierte Belege fuer ein "
            "ueberzeugendes Motivationsschreiben. "
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


def check_personal_motivation_sufficient(
    verified_motivations: list[MotivationEvidence],
) -> tuple[bool, str]:
    """Check whether personal motivation evidence is sufficient (CP-037R).

    Returns (is_sufficient, warning_message). A visible warning is raised
    when personal motivation evidence is insufficient.
    """
    personal = [
        m for m in verified_motivations
        if m.category in ("personal_motivation", "career_goal", "industry_interest")
        and m.confidence in ("high", "medium")
    ]
    if len(personal) < 1:
        return False, (
            "Insufficient personal motivation evidence. "
            "The letter may lack authentic personal drive. "
            "Consider adding motivation evidence in your career profile."
        )
    return True, ""


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


def build_structured_motivation_prompt(
    input_data: MotivationLetterInput,
    *,
    evidence_sufficient: bool = True,
) -> str:
    """Build a structured, anti-copying prompt for section-based generation (CP-037R).

    This prompt includes only selected verified evidence (not the full CV/JD),
    structured role context, company context, and selected requirements.
    The output format requires JSON with sections and evidence references.
    """
    language = normalize_output_language(input_data.output_language)

    motivation_lines = []
    for m in input_data.verified_motivations:
        motivation_lines.append(
            f"[{m.evidence_id}] ({m.category}, confidence={m.confidence}) {m.statement}"
        )
    motivation_text = "\n".join(motivation_lines) if motivation_lines else "(none)"

    experience_lines = []
    for e in input_data.verified_experiences:
        experience_lines.append(
            f"[{e.experience_id}] {e.role_title} at {e.company} ({e.period}): "
            f"{'; '.join(e.key_bullets)}"
        )
    experience_text = "\n".join(experience_lines) if experience_lines else "(none)"

    role_context = f"Role: {input_data.job_title} at {input_data.job_company}"
    company_context = input_data.company_context or f"Company: {input_data.job_company}"

    if input_data.role_requirements:
        req_text = "\n".join(f"- {r}" for r in input_data.role_requirements)
    else:
        req_text = "(use evidence to demonstrate fit for the role)"

    evidence_note = ""
    if not evidence_sufficient:
        evidence_note = (
            "\n\nIMPORTANT: Verified evidence is limited. Keep the letter concise "
            "and honest. Do NOT invent facts to compensate."
        )

    return MOTIVATION_GENERATION_PROMPT.format(
        output_language=language,
        candidate_name=input_data.candidate_name,
        job_title=input_data.job_title,
        job_company=input_data.job_company,
        motivation_evidence=motivation_text,
        experience_evidence=experience_text,
        role_context=role_context,
        company_context=company_context,
        requirements=req_text,
    ) + evidence_note


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
    """Generate a motivation letter (legacy API, delegates to CP-037R orchestrator)."""
    return generate_motivation_letter(
        deepseek_api_key=deepseek_api_key,
        deepseek_model=deepseek_model,
        job=job,
        cv_text=cv_text,
        candidate_name=candidate_name,
        verified_motivations=verified_motivations,
        verified_experiences=verified_experiences,
        company_context=company_context,
        role_requirements=role_requirements,
        output_language=output_language,
    )


# ---------------------------------------------------------------------------
# Anti-copying and claim validation (CP-037R)
# ---------------------------------------------------------------------------

_COPY_CHECK_MIN_LENGTH = 30


def _find_copied_segments(letter_text, source_text, *, min_length=_COPY_CHECK_MIN_LENGTH, source_label="source"):
    """Find segments of letter_text that appear verbatim in source_text."""
    copied = []
    if not letter_text or not source_text:
        return copied
    letter_lower = letter_text.lower()
    source_lower = source_text.lower()
    window = min_length
    max_window = min(200, len(letter_text))
    found_positions = set()
    while window <= max_window:
        for i in range(len(letter_text) - window + 1):
            if any(pos <= i < pos + window for pos in found_positions):
                continue
            chunk = letter_lower[i:i + window]
            if chunk in source_lower:
                found_positions.add(i)
                snippet = letter_text[i:i + min(window + 40, len(letter_text))]
                copied.append({"position": i, "length": window, "snippet": snippet.strip()[:80] + ("..." if len(snippet) > 80 else ""), "source_label": source_label})
        window += 5
    if copied:
        copied.sort(key=lambda x: (x["position"], -x["length"]))
        deduped = []
        last_end = -1
        for seg in copied:
            if seg["position"] >= last_end:
                deduped.append(seg)
                last_end = seg["position"] + seg["length"]
        copied = deduped
    return copied


def validate_letter_claims(letter_text, cv_text, job_description_text, *, min_copy_length=_COPY_CHECK_MIN_LENGTH):
    """Validate that the letter does not copy CV or JD text (CP-037R)."""
    issues = []
    cv_copies = _find_copied_segments(letter_text, cv_text, min_length=min_copy_length, source_label="CV")
    jd_copies = _find_copied_segments(letter_text, job_description_text, min_length=min_copy_length, source_label="Job Description")
    if cv_copies:
        issues.append(f"Found {len(cv_copies)} segment(s) copied from CV (min {min_copy_length} chars).")
    if jd_copies:
        issues.append(f"Found {len(jd_copies)} segment(s) copied from Job Description (min {min_copy_length} chars).")
    return {"passed": len(issues) == 0, "issues": issues, "cv_copies": cv_copies, "jd_copies": jd_copies}


def validate_section_evidence_refs(sections, verified_motivations, verified_experiences):
    """Validate that section evidence_refs reference actual verified evidence (CP-037R)."""
    valid_motivation_ids = {m.evidence_id for m in verified_motivations}
    valid_experience_ids = {e.experience_id for e in verified_experiences}
    all_valid_ids = valid_motivation_ids | valid_experience_ids
    issues = []
    for section in sections:
        for ref in section.evidence_refs:
            if ref not in all_valid_ids:
                issues.append(f"Section '{section.heading}' references unknown evidence '{ref}'. Valid IDs: {sorted(all_valid_ids)}")
    return {"passed": len(issues) == 0, "issues": issues, "valid_ids": sorted(all_valid_ids)}


# ---------------------------------------------------------------------------
# Section parsing (CP-037R)
# ---------------------------------------------------------------------------

def _extract_evidence_refs(text):
    """Extract evidence references like [ev_*] or [profile_*]."""
    pattern = re.compile(r"\[([a-zA-Z_][a-zA-Z0-9_]*)\]")
    return list(dict.fromkeys(
        m.group(1) for m in pattern.finditer(text)
        if "ev_" in m.group(1).lower() or "profile_" in m.group(1).lower()
    ))


def _split_by_headings(text, heading_patterns):
    """Split text by known section headings."""
    result = {}
    if not text.strip():
        return result
    lines = text.split("\n")
    current_heading = None
    current_lines = []
    used_headings = set()
    for line in lines:
        stripped = line.strip()
        matched = False
        for pattern, key in heading_patterns:
            if stripped.lower().startswith(pattern.lower()) and key not in used_headings:
                if current_heading:
                    result[current_heading] = "\n".join(current_lines).strip()
                current_heading = pattern
                current_lines = [stripped]
                used_headings.add(key)
                matched = True
                break
        if not matched:
            if current_heading:
                current_lines.append(line)
            else:
                current_lines.append(line)
    if current_heading:
        result[current_heading] = "\n".join(current_lines).strip()
    elif current_lines and not result:
        result["Body"] = "\n".join(current_lines).strip()
    return result


def parse_letter_sections(letter_text, output_language="English"):
    """Parse a plain-text motivation letter into sections with evidence references (CP-037R)."""
    labels = MOTIVATION_LETTER_LABELS.get(
        normalize_output_language(output_language),
        MOTIVATION_LETTER_LABELS["English"],
    )
    sections = []
    if not letter_text.strip():
        return sections

    heading_patterns = [
        (labels["section_why_role"], "why_role"),
        (labels["section_why_company"], "why_company"),
        (labels["section_fit"], "fit"),
        (labels["section_closing"], "closing"),
        ("Why This Role", "why_role"),
        ("Why", "why_company"),
        ("My Fit", "fit"),
        ("Closing", "closing"),
        ("Warum diese Position", "why_role"),
        ("Warum", "why_company"),
        ("Meine Eignung", "fit"),
        ("Abschluss", "closing"),
    ]

    lines = letter_text.strip().split("\n")
    greeting_line = ""
    closing_line = ""
    body_start = 0
    body_end = len(lines)

    for i, line in enumerate(lines[:5]):
        stripped = line.strip()
        if stripped and (
            stripped.lower().startswith("dear ")
            or stripped.lower().startswith("sehr ")
            or stripped.lower().startswith("hello")
            or stripped.lower().startswith("to whom")
        ):
            greeting_line = stripped
            body_start = i + 1
            break

    for i in range(len(lines) - 1, max(body_start, len(lines) - 8), -1):
        stripped = lines[i].strip()
        if stripped and (
            stripped.lower().startswith("sincerely")
            or stripped.lower().startswith("best regards")
            or stripped.lower().startswith("kind regards")
            or stripped.lower().startswith("mit freundlichen")
            or stripped.lower().startswith("yours")
            or stripped.lower().startswith("regards")
        ):
            closing_line = stripped
            body_end = i
            break

    body_lines = lines[body_start:body_end]
    body_text = "\n".join(body_lines).strip()

    if greeting_line:
        sections.append(MotivationLetterSection(
            heading=labels.get("greeting", "Greeting"),
            body=greeting_line,
            evidence_refs=_extract_evidence_refs(greeting_line),
        ))

    section_map = _split_by_headings(body_text, heading_patterns)
    for heading, content in section_map.items():
        sections.append(MotivationLetterSection(
            heading=heading,
            body=content.strip(),
            evidence_refs=_extract_evidence_refs(content),
        ))

    if closing_line:
        sections.append(MotivationLetterSection(
            heading=labels.get("closing", "Closing"),
            body=closing_line,
            evidence_refs=_extract_evidence_refs(closing_line),
        ))

    if len(sections) <= 1 and body_text:
        sections = [
            s for s in sections
            if s.heading not in (labels.get("greeting", "Greeting"),)
        ]
        sections.append(MotivationLetterSection(
            heading=labels.get("section_fit", "Letter Body"),
            body=body_text,
            evidence_refs=_extract_evidence_refs(body_text),
        ))

    return sections


# ---------------------------------------------------------------------------
# Main orchestrator: generate_motivation_letter (CP-037R)
# ---------------------------------------------------------------------------

def generate_motivation_letter(
    deepseek_api_key, deepseek_model, job, cv_text, candidate_name,
    verified_motivations=None, verified_experiences=None,
    company_context="", role_requirements=None, output_language="English",
    *, skip_api_call=False,
):
    """Generate a structured, evidence-backed motivation letter (CP-037R)."""
    motivations = verified_motivations or []
    experiences = verified_experiences or []
    requirements = role_requirements or []
    job_id = str(job.get("job_id", ""))
    job_title = str(job.get("title", ""))
    job_company = str(job.get("company", ""))
    job_description = str(job.get("full_description", ""))
    language = normalize_output_language(output_language)

    # 1. Evidence sufficiency assessment
    is_sufficient, sw = assess_evidence_sufficiency(motivations, experiences)
    personal_ok, pw = check_personal_motivation_sufficient(motivations)
    all_warnings = list(sw)
    if not personal_ok:
        all_warnings.append(pw)
    evidence_insufficient = not is_sufficient or not personal_ok

    # 2. Build prompt
    input_data = MotivationLetterInput(
        candidate_name=candidate_name, job_title=job_title,
        job_company=job_company, job_description_text=job_description,
        cv_text=cv_text, verified_experiences=experiences,
        verified_motivations=motivations, company_context=company_context,
        role_requirements=requirements, output_language=language)

    if skip_api_call:
        return MotivationLetterResult(
            job_id=job_id, candidate_name=candidate_name,
            letter_text="", sections=[],
            motivation_evidence_count=len(motivations),
            experience_evidence_count=len(experiences),
            evidence_insufficient=evidence_insufficient,
            insufficient_warning="; ".join(all_warnings) if all_warnings else "",
            output_language=language,
            error="API call skipped (test mode)")

    if not deepseek_api_key:
        return MotivationLetterResult(
            job_id=job_id, candidate_name=candidate_name,
            letter_text="", sections=[],
            motivation_evidence_count=len(motivations),
            experience_evidence_count=len(experiences),
            evidence_insufficient=True,
            insufficient_warning="Missing DeepSeek API key.",
            output_language=language)

    # 3. Call DeepSeek
    prompt = build_structured_motivation_prompt(
        input_data, evidence_sufficient=not evidence_insufficient)
    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {deepseek_api_key}",
                     "Content-Type": "application/json"},
            json={"model": deepseek_model, "messages": [
                {"role": "system", "content": ANTI_COPY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}],
                "temperature": 0.5}, timeout=90)
        response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return MotivationLetterResult(
            job_id=job_id, candidate_name=candidate_name,
            letter_text="", sections=[],
            motivation_evidence_count=len(motivations),
            experience_evidence_count=len(experiences),
            evidence_insufficient=True,
            insufficient_warning=(
                "; ".join(all_warnings) if all_warnings else "Generation failed."),
            output_language=language,
            error=f"DeepSeek API error: {exc}")

    # 4. Parse JSON response
    try:
        parsed = json.loads(strip_json_fences(raw_content))
        letter_text = str(parsed.get("letter_text", ""))
        raw_sections = parsed.get("sections", [])
    except (json.JSONDecodeError, TypeError):
        letter_text = raw_content
        raw_sections = []

    sections = []
    if raw_sections and isinstance(raw_sections, list):
        for sec in raw_sections:
            if isinstance(sec, dict):
                sections.append(MotivationLetterSection(
                    heading=str(sec.get("heading", "")),
                    body=str(sec.get("body", "")),
                    evidence_refs=[
                        str(r) for r in (sec.get("evidence_refs") or [])]))
    else:
        sections = parse_letter_sections(letter_text, language)

    # 5. Validate
    cv = validate_letter_claims(
        letter_text, cv_text, job_description,
        min_copy_length=_COPY_CHECK_MIN_LENGTH)
    ev = validate_section_evidence_refs(sections, motivations, experiences)
    if not cv["passed"]:
        all_warnings.extend(cv["issues"])
    if not ev["passed"]:
        all_warnings.extend(ev["issues"])

    # 6. Build final warning
    labels = MOTIVATION_LETTER_LABELS.get(
        language, MOTIVATION_LETTER_LABELS["English"])
    if evidence_insufficient:
        if not personal_ok:
            wm = labels.get("insufficient_warning_motivation",
                            labels["insufficient_warning_general"])
        elif len(experiences) < MINIMUM_EXPERIENCE_EVIDENCE_POINTS:
            wm = labels.get("insufficient_warning_experience",
                            labels["insufficient_warning_general"])
        else:
            wm = labels.get("insufficient_warning_general", "")
    else:
        wm = ""
    if all_warnings:
        wm = "; ".join(dict.fromkeys(all_warnings))

    return MotivationLetterResult(
        job_id=job_id, candidate_name=candidate_name,
        letter_text=letter_text, sections=sections,
        motivation_evidence_count=len(motivations),
        experience_evidence_count=len(experiences),
        evidence_insufficient=evidence_insufficient,
        insufficient_warning=wm,
        output_language=language)
