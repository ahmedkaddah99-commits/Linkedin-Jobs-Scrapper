"""Profile-only, explainable matching. No CV, preferences, or provider calls.

Scores measure supported coverage under a versioned rubric, not hiring odds.
The shared feature projection is built on the VPS and fenced to source versions.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from functools import lru_cache

VERSION = "profile_match_v1"
FEATURE_VERSION = "profile_job_facts_v1"

# Deliberately explicit equivalences; related technologies are not synonyms.
SKILLS = {
    "Python": ["python"], "SQL": ["sql"], "Java": ["java"],
    "JavaScript": ["javascript", "js"], "TypeScript": ["typescript"],
    "React": ["react", "reactjs"], "Angular": ["angular"], "Vue": ["vue", "vuejs"],
    "C++": ["c++"], "C#": ["c#"], "Go": ["golang"], "Rust": ["rust"],
    "PHP": ["php"], "Ruby": ["ruby"], "R": ["r programming", "r-programmierung"],
    "PostgreSQL": ["postgresql", "postgres"], "MySQL": ["mysql"], "MongoDB": ["mongodb"],
    "AWS": ["aws", "amazon web services"], "Azure": ["azure"],
    "Google Cloud": ["google cloud", "gcp"], "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"], "Terraform": ["terraform"],
    "Git": ["git"], "CI/CD": ["ci/cd", "continuous integration", "continuous delivery"],
    "Linux": ["linux"], "Excel": ["excel"], "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"], "SAP": ["sap"], "Salesforce": ["salesforce"],
    "Jira": ["jira"], "Confluence": ["confluence"], "Figma": ["figma"],
    "Scrum": ["scrum"], "Agile": ["agile", "agiles arbeiten"],
    "Project management": ["project management", "projektmanagement"],
    "Requirements analysis": ["requirements analysis", "requirements engineering", "anforderungsanalyse", "anforderungsmanagement"],
    "Business analysis": ["business analysis", "business-analysis", "geschäftsanalyse"],
    "Data analysis": ["data analysis", "data analytics", "datenanalyse"],
    "Stakeholder management": ["stakeholder management", "stakeholder-management"],
    "Process improvement": ["process improvement", "process optimization", "prozessoptimierung"],
    "SDLC": ["sdlc", "software development lifecycle", "software development life cycle"],
    "Machine learning": ["machine learning", "maschinelles lernen"],
    "Generative AI": ["generative ai", "genai", "generative ki"],
    "Accounting": ["accounting", "buchhaltung"], "Controlling": ["controlling"],
    "Financial planning": ["financial planning", "finanzplanung", "fp&a"],
    "Budgeting": ["budgeting", "budgetierung"], "Forecasting": ["forecasting", "prognoseplanung"],
    "SEO": ["seo", "search engine optimization", "suchmaschinenoptimierung"],
    "Google Analytics": ["google analytics", "ga4"], "CRM": ["crm", "customer relationship management"],
    "Customer service": ["customer service", "kundenservice", "kundenbetreuung"],
    "Negotiation": ["negotiation", "verhandlungsführung"],
    "Business development": ["business development", "geschäftsentwicklung"],
    "Supply chain": ["supply chain", "lieferkettenmanagement"],
    "Inventory management": ["inventory management", "bestandsmanagement"],
    "Quality assurance": ["quality assurance", "qualitätssicherung"],
    "Testing": ["software testing", "application testing", "softwaretests"],
    "Recruiting": ["recruiting", "recruitment", "personalbeschaffung"],
    "Payroll": ["payroll", "lohnabrechnung", "gehaltsabrechnung"],
}
INDUSTRIES = {
    "Insurance": ["insurance", "versicherung", "versicherungen"],
    "Banking": ["banking", "bankwesen", "bank"],
    "Financial services": ["financial services", "finanzdienstleistungen", "finance"],
    "Software": ["software", "saas"], "Information technology": ["information technology", "it services", "informationstechnologie"],
    "Consulting": ["consulting", "consultancy", "unternehmensberatung"],
    "Manufacturing": ["manufacturing", "fertigung", "industrial manufacturing"],
    "Automotive": ["automotive", "automobil", "automobilindustrie"],
    "Retail": ["retail", "einzelhandel"], "Wholesale": ["wholesale", "großhandel"],
    "Logistics": ["logistics", "logistik"], "Mobility": ["mobility", "mobilität"],
    "Healthcare": ["healthcare", "health care", "gesundheitswesen"],
    "Pharmaceuticals": ["pharmaceuticals", "pharmaceutical", "pharma"],
    "Energy": ["energy", "energie", "utilities"],
    "Construction": ["construction", "bauwesen", "bauindustrie"],
    "Education": ["education", "bildung", "higher education"],
    "Telecommunications": ["telecommunications", "telekommunikation"],
    "Real estate": ["real estate", "immobilien"],
    "Hospitality": ["hospitality", "hotellerie", "hotel"],
    "Public sector": ["public sector", "government", "öffentlicher dienst"],
    "Media": ["media", "medien"], "Aerospace": ["aerospace", "luftfahrt"],
}
# Related domains earn partial credit, never full equivalence.
RELATED_INDUSTRIES = [{"Insurance", "Banking", "Financial services"},
                      {"Software", "Information technology"},
                      {"Automotive", "Mobility", "Manufacturing"},
                      {"Retail", "Wholesale", "Logistics"}, {"Healthcare", "Pharmaceuticals"}]
LEVELS = {"intern": 0, "entry": 1, "mid": 2, "senior": 3, "lead": 4, "director": 5, "executive": 6}
PROFILE_FIELDS = ("role_title", "summary", "industry", "skills", "competencies", "recent_experience", "experience", "education", "languages", "projects", "certifications")


def text(value) -> str:
    if isinstance(value, Mapping):
        return " ".join(text(value.get(k)) for k in ("text", "value", "label", "name", "title", "description", "summary", "bullets", "bulletsText", "details"))
    if isinstance(value, list):
        return " ".join(text(v) for v in value)
    return str(value or "")


@lru_cache(maxsize=2048)
def pattern(term):
    return re.compile(r"(?<![\w+#])" + re.escape(term).replace(r"\ ", r"[\s-]+") + r"(?![\w+#])", re.I)


def mentions(term, value):
    return bool(pattern(term).search(text(value)))


def supports(term, value):
    value = text(value)
    for match in pattern(term).finditer(value):
        prefix = value[max(0, match.start() - 45):match.start()]
        if not re.search(r"\b(no|not|never|lack|lacking|without|kein|keine|keinen|nicht|ohne)\b[^.;\n]*$", prefix, re.I):
            return True
    return False


def concepts(value, taxonomy):
    return {name for name, aliases in taxonomy.items() if any(mentions(alias, value) for alias in aliases)}


def decoded(value):
    if isinstance(value, Mapping):
        return dict(value)
    try:
        return json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}


def profile_snapshot(user):
    metadata = getattr(user, "metadata", {}) or {}
    raw = metadata.get("profile") or {}
    profile = {key: raw.get(key) for key in PROFILE_FIELDS if raw.get(key) not in (None, "", [])}
    digest = hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"data": profile, "version_id": digest, "source": "saved_profile"}


def build_job_facts(row):
    """Only consume source-bound enrichment and exact source-supported skill labels."""
    summary = decoded(row.get("summary_json"))
    filters = decoded(row.get("filters_json"))
    payload = decoded(row.get("payload_json") or row.get("version_payload_json"))
    source = text(row.get("description"))
    required = summary.get("required_qualifications") or summary.get("essential_requirements") or []
    preferred = summary.get("preferred_qualifications") or []
    skills = {}
    for kind, passages in (("preferred", preferred), ("required", required)):
        for passage in passages:
            for skill in concepts(passage, SKILLS):
                if concepts(source, {skill: SKILLS[skill]}):
                    skills[skill] = {"name": skill, "requiredness": kind, "job_evidence": text(passage)}
    # Open vocabulary labels must occur verbatim in the original posting and
    # in a qualification. No skill inference from employer marketing text.
    for value in filters.get("skills") or []:
        label = text(value).strip()
        if not label or len(label) > 80 or not mentions(label, source):
            continue
        canonical = next(iter(concepts(label, SKILLS)), label)
        if canonical in skills:
            continue
        for kind, passages in (("required", required), ("preferred", preferred)):
            evidence = next((text(p) for p in passages if mentions(label, p)), None)
            if evidence:
                skills[canonical] = {"name": canonical, "requiredness": kind, "job_evidence": evidence}
                break
    company = decoded(row.get("company_profile_json"))
    industry_record = (company.get("fields") or company).get("industry") or {}
    industry = industry_record.get("value") if isinstance(industry_record, Mapping) and industry_record.get("state") == "known" else payload.get("industry")
    # Preserve explicit, unknown-taxonomy source labels for exact comparison.
    industries = sorted(concepts(industry, INDUSTRIES)) or ([text(industry)] if industry else [])
    years = filters.get("required_experience_years", filters.get("experience_years_min"))
    if not isinstance(years, (int, float)) or isinstance(years, bool) or not 0 <= years <= 60:
        years = None
    levels = filters.get("experience_levels") or filters.get("experience_level") or []
    if isinstance(levels, str):
        levels = [levels]
    return {"version": FEATURE_VERSION, "skills": list(skills.values()), "years_min": years,
            "levels": [v for v in levels if v in LEVELS], "industries": industries,
            "roles": filters.get("roles") or [], "title": text(row.get("title")),
            "source_ready": bool(summary), "posting_version": row.get("version_id") or row.get("current_version_id"),
            "content_hash": row.get("content_hash"),
            "input_hash": hashlib.sha256(json.dumps([summary, filters, industry], sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


def experience_text(item):
    return " ".join(text(item.get(k)) for k in ("title", "role", "description", "summary", "bullets", "bulletsText", "skills"))


def month(value, *, today, end=False):
    value = text(value).strip().casefold()
    if value in {"present", "current", "today", "heute", "aktuell", "ongoing"}:
        return today.year * 12 + today.month
    match = re.fullmatch(r"(\d{4})(?:-(\d{1,2})(?:-\d{2})?)?", value)
    if not match:
        return None
    year, mm = int(match[1]), int(match[2] or (12 if end else 1))
    return year * 12 + mm if 1950 <= year <= today.year and 1 <= mm <= 12 else None


def interval(item, today):
    start, end = item.get("start_date") or item.get("start"), item.get("end_date") or item.get("end")
    if not start:
        period = text(item.get("period"))
        values = re.findall(r"\d{4}(?:-\d{2})?|present|current|heute|aktuell", period, re.I)
        if len(values) == 2:
            start, end = values
    a, b = month(start, today=today), month(end, today=today, end=True)
    cap = today.year * 12 + today.month
    return (a, min(b, cap)) if a is not None and b is not None and a < b else None


def union_years(intervals):
    total, end = 0, -1
    for a, b in sorted(intervals):
        total += max(0, b - max(a, end))
        end = max(end, b)
    return total / 12


def title_level(title):
    for level, regex in ((6, r"\b(ceo|cto|cfo|chief|vp|vice president)\b"),
                         (5, r"\b(director|head of|direktor)\b"),
                         (4, r"\b(lead|teamleiter|team lead|principal|staff)\b"),
                         (3, r"\b(senior|sr)\b"), (1, r"\b(junior|entry|associate|graduate)\b"),
                         (0, r"\b(intern|praktikant|werkstudent)\b")):
        if re.search(regex, title, re.I):
            return level
    return None


def role_words(value):
    return set(re.findall(r"\w{3,}", text(value).casefold())) - {"senior", "junior", "associate", "manager", "lead", "the", "and", "for", "with", "und", "von", "der", "die", "das", "level", "entry", "mwd"}


def evaluate_profile_match(facts, snapshot, *, today=None):
    today = today or date.today()
    p = snapshot.get("data") or {}
    if not p:
        return {"state": "needs_profile", "score": None, "dimensions": {}, "profile_version": snapshot.get("version_id"), "evaluator_version": VERSION}
    if not facts or facts.get("version") != FEATURE_VERSION:
        return {"state": "pending", "score": None, "dimensions": {}, "evaluator_version": VERSION}
    experiences = [x for x in (p.get("recent_experience") or p.get("experience") or []) if isinstance(x, Mapping)]
    support = [("Profile skills", text([p.get("skills"), p.get("competencies")]))]
    support += [(text(x.get("title") or x.get("role")) or "Work experience", experience_text(x)) for x in experiences]
    support += [("Project", text(x)) for x in p.get("projects") or []]
    mappings = []
    for skill in facts.get("skills") or []:
        name = skill["name"]
        aliases = SKILLS.get(name, [name])
        found = next(((label, value) for label, value in support if any(supports(a, value) for a in aliases)), None)
        mappings.append({**skill, "status": "supported" if found else "not_evidenced",
                         "profile_evidence": found[1] if found else None, "profile_source": found[0] if found else None})
    denominator = sum(2 if s["requiredness"] == "required" else 1 for s in mappings)
    numerator = sum((2 if s["requiredness"] == "required" else 1) for s in mappings if s["status"] == "supported")
    skill_score = round(100 * numerator / denominator) if denominator else None
    job_skills = {s["name"] for s in mappings}
    job_words = role_words([facts.get("title"), facts.get("roles")])
    relevant = []
    for item in experiences:
        words = role_words(item.get("title") or item.get("role"))
        title_fit = bool(words and job_words and len(words & job_words) / min(len(words), len(job_words)) >= 0.67)
        overlap = concepts(experience_text(item), SKILLS) & job_skills
        skill_fit = len(overlap) >= 2 and len(overlap) / max(1, len(job_skills)) >= 0.5
        if title_fit or skill_fit:
            relevant.append(item)
    intervals = [value for item in relevant if (value := interval(item, today))]
    years = union_years(intervals)
    year_score = None
    if facts.get("years_min") is not None and intervals and len(intervals) == len(relevant):
        year_score = 100 if facts["years_min"] == 0 else round(100 * min(1, years / facts["years_min"]))
    required_level = min((LEVELS[v] for v in facts.get("levels") or []), default=None)
    established_levels = [v for item in relevant if (v := title_level(text(item.get("title") or item.get("role")))) is not None]
    # Dated relevant work can establish a conservative band when titles omit it.
    if intervals and len(intervals) == len(relevant):
        established_levels.append(1 if years < 2 else 2 if years < 5 else 3)
    candidate_level = max(established_levels, default=None)
    level_score = None
    if required_level is not None and candidate_level is not None:
        level_score = 100 if candidate_level >= required_level else round(100 * (candidate_level + 1) / (required_level + 1))
    scores = [v for v in (year_score, level_score) if v is not None]
    exp_score = min(scores) if scores else None
    # Explicit profile/work industries only; never guess from employer names.
    profile_industry_text = [p.get("industry")] + [x.get("industry") for x in experiences]
    candidate_industries = concepts(profile_industry_text, INDUSTRIES)
    industry_mappings = []
    for industry in facts.get("industries") or []:
        exact = industry in candidate_industries or any(mentions(industry, v) for v in profile_industry_text)
        related = any(industry in group and bool(candidate_industries & group) for group in RELATED_INDUSTRIES)
        industry_mappings.append({"industry": industry, "status": "direct" if exact else "related" if related else "not_evidenced", "credit": 1 if exact else 0.5 if related else 0})
    has_industry = bool(text(profile_industry_text).strip())
    industry_score = round(100 * sum(x["credit"] for x in industry_mappings) / len(industry_mappings)) if industry_mappings and has_industry else None
    dimensions = {
        "experience_level": {"label": "Experience Level", "score": exp_score, "relevant_years": round(years, 2) if intervals else None,
                             "required_years": facts.get("years_min"), "required_levels": facts.get("levels"),
                             "profile_evidence": [experience_text(x) for x in relevant],
                             "explanation": "Relevant dated work is counted once across overlapping roles. The lower of years coverage and seniority coverage is used when both are established."},
        "skill": {"label": "Skill", "score": skill_score, "mappings": mappings,
                  "explanation": "Source-supported required skills count twice; preferred skills count once. Exact names and reviewed English/German aliases receive full credit."},
        "industry_experience": {"label": "Industry Exp.", "score": industry_score, "mappings": industry_mappings,
                                "profile_industries": sorted(candidate_industries),
                                "explanation": "Explicit profile industries earn full credit for direct overlap and half credit for documented related domains. Company names do not establish industry experience."},
    }
    known = [d["score"] for d in dimensions.values() if d["score"] is not None]
    overall = round(sum(known) / len(known)) if known else None
    return {"state": "available" if len(known) == 3 else "partial" if known else "insufficient_information",
            "score": overall, "label": "Partial assessment" if known and len(known) < 3 else "Strong match" if overall is not None and overall >= 80 else "Good match" if overall is not None and overall >= 60 else "Partial match" if overall is not None else "Insufficient information",
            "dimensions": dimensions, "coverage": len(known), "evaluator_version": VERSION,
            "profile_version": snapshot.get("version_id"), "profile_source": "saved_profile",
            "posting_version": facts.get("posting_version"),
            "formula": "Arithmetic mean of established dimensions; unavailable dimensions remain unknown. Provisional fit rubric, not a probability or Jobright's proprietary formula.",
            "missing_keywords": [s["name"] for s in mappings if s["status"] != "supported"],
            "matched_keywords": [s["name"] for s in mappings if s["status"] == "supported"]}
