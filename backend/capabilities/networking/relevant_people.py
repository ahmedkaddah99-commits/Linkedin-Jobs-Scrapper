from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.domain.models import JobRecord, utc_now_iso

from .outreach import (
    _TARGET_DISCIPLINE_LIBRARY,
    _infer_target_contact_discipline,
    _target_contact_location_hint,
    build_target_contact_discovery,
    company_names_safely_match,
)

PEOPLE_DISCOVERY_STATUS_NOT_STARTED = "not_started"
PEOPLE_DISCOVERY_STATUS_RUNNING = "running"
PEOPLE_DISCOVERY_STATUS_COMPLETED = "completed"
PEOPLE_DISCOVERY_STATUS_FAILED = "failed"
PEOPLE_DISCOVERY_STATUS_NOT_CONFIGURED = "not_configured"

LIVE_DISCOVERY_NOT_CONFIGURED_ERROR = (
    "Live networking discovery is disabled. Set RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY=1 "
    "and restart the backend to search public profiles."
)
LIVE_DISCOVERY_SEARCH_FAILED_ERROR = (
    "Public profile search failed before any usable results were returned. "
    "DuckDuckGo may have returned an anti-bot challenge. Try again later or configure "
    "a more reliable search provider."
)

PEOPLE_CATEGORY_HIRING_MANAGER = "hiring_manager"
PEOPLE_CATEGORY_POTENTIAL_COLLEAGUE = "potential_colleague"
PEOPLE_CATEGORY_EXECUTIVE = "executive"
PEOPLE_CATEGORIES = (
    PEOPLE_CATEGORY_HIRING_MANAGER,
    PEOPLE_CATEGORY_POTENTIAL_COLLEAGUE,
    PEOPLE_CATEGORY_EXECUTIVE,
)

PEOPLE_CATEGORY_LABELS = {
    PEOPLE_CATEGORY_HIRING_MANAGER: "Hiring Manager",
    PEOPLE_CATEGORY_POTENTIAL_COLLEAGUE: "Potential Colleague",
    PEOPLE_CATEGORY_EXECUTIVE: "Executive",
}

_FINAL_CATEGORY_BY_LANE = {
    "direct_hiring_chain": PEOPLE_CATEGORY_HIRING_MANAGER,
    "peer_context": PEOPLE_CATEGORY_POTENTIAL_COLLEAGUE,
    "leadership": PEOPLE_CATEGORY_EXECUTIVE,
}
_CONFIDENCE_LABELS = (
    (80, "High"),
    (55, "Medium"),
    (0, "Low"),
)
_TITLE_KEYWORDS_BY_CATEGORY = {
    PEOPLE_CATEGORY_HIRING_MANAGER: (
        "head",
        "manager",
        "lead",
        "director",
        "supervisor",
        "team lead",
        "principal manager",
    ),
    PEOPLE_CATEGORY_POTENTIAL_COLLEAGUE: (
        "specialist",
        "analyst",
        "associate",
        "coordinator",
        "engineer",
        "consultant",
        "advisor",
        "partner",
        "staff",
        "senior",
        "representative",
    ),
    PEOPLE_CATEGORY_EXECUTIVE: (
        "vp",
        "vice president",
        "chief",
        "country manager",
        "general manager",
        "managing director",
        "regional director",
        "director",
        "head",
    ),
}
_SENIORITY_KEYWORDS = {
    "executive": ("chief", "vp", "vice president", "managing director", "general manager", "country manager"),
    "director": ("director", "regional director"),
    "manager": ("manager", "head", "lead", "supervisor"),
    "individual_contributor": ("specialist", "analyst", "associate", "coordinator", "engineer", "consultant"),
}
_KEYWORD_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "role",
    "senior",
    "team",
    "the",
    "to",
    "with",
}
_PERSON_SUFFIX_BLOCKLIST = {
    "gmbh",
    "inc",
    "llc",
    "ltd",
    "corp",
    "company",
    "linkedin",
    "careers",
    "jobs",
    "team",
    "department",
}
_REGIONAL_SCOPE_PATTERN = re.compile(
    r"\b(dach|emea|apac|global|regional|region|country|europe|germany|france|uk|european)\b",
    re.IGNORECASE,
)
_WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9&+/#.-]*")


@dataclass(slots=True)
class SearchHypothesis:
    hypothesis_id: str
    pass_index: int
    category: str
    title_query: str = ""
    keyword_query: str = ""
    location_modifiers: list[str] = field(default_factory=list)
    confidence_before_search: int = 0
    explanation: str = ""
    discovered_query: str = ""
    lane: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.hypothesis_id,
            "passIndex": self.pass_index,
            "category": self.category,
            "titleQuery": self.title_query,
            "keywordQuery": self.keyword_query,
            "locationModifiers": list(self.location_modifiers),
            "confidenceBeforeSearch": self.confidence_before_search,
            "explanation": self.explanation,
            "discoveredQuery": self.discovered_query,
            "lane": self.lane,
        }


@dataclass(slots=True)
class PublicProfileCandidate:
    candidate_id: str
    pass_index: int
    category: str
    name: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    profile_url: str = ""
    source: str = ""
    search_query: str = ""
    evidence_snippets: list[str] = field(default_factory=list)
    match_summary: str = ""
    lane: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.candidate_id,
            "passIndex": self.pass_index,
            "category": self.category,
            "name": self.name,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "profileUrl": self.profile_url,
            "source": self.source,
            "searchQuery": self.search_query,
            "evidenceSnippets": list(self.evidence_snippets),
            "matchSummary": self.match_summary,
            "lane": self.lane,
        }


@dataclass(slots=True)
class ConfidenceBreakdown:
    company_match: int
    title_category_match: int
    department_function_match: int
    location_region_match: int
    seniority_fit: int
    business_unit_relevance: int
    profile_freshness: int
    source_reliability: int
    evidence_quality: int
    total: int
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "companyMatch": self.company_match,
            "titleCategoryMatch": self.title_category_match,
            "departmentFunctionMatch": self.department_function_match,
            "locationRegionMatch": self.location_region_match,
            "seniorityFit": self.seniority_fit,
            "businessUnitRelevance": self.business_unit_relevance,
            "profileFreshness": self.profile_freshness,
            "sourceReliability": self.source_reliability,
            "evidenceQuality": self.evidence_quality,
            "total": self.total,
            "label": self.label,
        }


@dataclass(slots=True)
class RelevantPerson:
    person_id: str
    category: str
    name: str
    title: str = ""
    company: str = ""
    location: str = ""
    profile_url: str = ""
    source: str = "public_profile_search"
    confidence: int = 0
    confidence_label: str = "Low"
    reasoning_note: str = ""
    evidence_snippets: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    discovered_search_query: str = ""
    region_scope_caveat: str = ""
    confidence_breakdown: ConfidenceBreakdown | None = None
    status: str = "unreviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.person_id,
            "category": self.category,
            "name": self.name,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "profileUrl": self.profile_url,
            "source": self.source,
            "confidence": self.confidence,
            "confidenceLabel": self.confidence_label,
            "reasoningNote": self.reasoning_note,
            "evidenceSnippets": list(self.evidence_snippets),
            "caveats": list(self.caveats),
            "searchQueries": list(self.search_queries),
            "discoveredSearchQuery": self.discovered_search_query,
            "regionScopeCaveat": self.region_scope_caveat,
            "confidenceBreakdown": (
                self.confidence_breakdown.to_dict() if self.confidence_breakdown else None
            ),
            "status": self.status,
        }


@dataclass(slots=True)
class PeopleDiscoveryRun:
    run_id: str
    workspace_id: str
    job_id: str
    company: str
    job_title: str
    people_discovery_status: str
    context_extraction: dict[str, Any]
    categories: dict[str, list[RelevantPerson]]
    search_hypotheses: list[SearchHypothesis] = field(default_factory=list)
    public_profile_candidates: list[PublicProfileCandidate] = field(default_factory=list)
    passes: list[dict[str, Any]] = field(default_factory=list)
    provider: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    last_started_at: str = ""
    last_completed_at: str = ""
    last_updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        selected_people = [
            person.to_dict()
            for category in PEOPLE_CATEGORIES
            for person in self.categories.get(category, [])
            if person.status in {"confirmed", "saved_for_outreach"}
        ]
        return {
            "runId": self.run_id,
            "workspaceId": self.workspace_id,
            "jobId": self.job_id,
            "company": self.company,
            "jobTitle": self.job_title,
            "peopleDiscoveryStatus": self.people_discovery_status,
            "contextExtraction": dict(self.context_extraction),
            "searchHypotheses": [item.to_dict() for item in self.search_hypotheses],
            "publicProfileCandidates": [item.to_dict() for item in self.public_profile_candidates],
            "categories": {
                category: [person.to_dict() for person in self.categories.get(category, [])]
                for category in PEOPLE_CATEGORIES
            },
            "passes": list(self.passes),
            "provider": dict(self.provider),
            "warnings": list(self.warnings),
            "selectedPeople": selected_people,
            "error": self.error,
            "lastStartedAt": self.last_started_at,
            "lastCompletedAt": self.last_completed_at,
            "lastUpdatedAt": self.last_updated_at,
        }


def build_empty_relevant_people_discovery(
    *,
    job: JobRecord,
    run_id: str = "",
    workspace_id: str = "",
    status: str = PEOPLE_DISCOVERY_STATUS_NOT_STARTED,
    error: str = "",
    last_started_at: str = "",
    last_completed_at: str = "",
) -> dict[str, Any]:
    context = _build_context_extraction(job=job)
    return PeopleDiscoveryRun(
        run_id=run_id,
        workspace_id=workspace_id,
        job_id=str(job.job_id or ""),
        company=str(job.company or ""),
        job_title=str(job.title or ""),
        people_discovery_status=status,
        context_extraction=context,
        categories={category: [] for category in PEOPLE_CATEGORIES},
        error=error,
        last_started_at=last_started_at,
        last_completed_at=last_completed_at,
        last_updated_at=utc_now_iso(),
    ).to_dict()


def build_relevant_people_discovery(
    *,
    profile: dict[str, Any],
    job: JobRecord,
    run_id: str = "",
    workspace_id: str = "",
    search_provider: Callable[..., list[dict[str, Any]]] | None = None,
    ai_provider: Callable[..., dict[str, Any]] | None = None,
    last_started_at: str = "",
) -> dict[str, Any]:
    discovery_payload = build_target_contact_discovery(
        profile=profile,
        job=job,
        search_provider=search_provider,
        ai_provider=ai_provider,
    )
    context = _build_context_extraction(job=job, discovery_payload=discovery_payload)
    hypotheses = _build_search_hypotheses(job=job, discovery_payload=discovery_payload, context=context)
    public_profile_candidates = _build_public_profile_candidates(
        discovery_payload=discovery_payload,
        hypotheses=hypotheses,
    )
    categories = _build_relevant_people_categories(
        job=job,
        discovery_payload=discovery_payload,
        context=context,
        public_profile_candidates=public_profile_candidates,
    )
    discovery_status, discovery_error = _status_for_discovery_payload(discovery_payload)
    completed_at = utc_now_iso() if discovery_status == PEOPLE_DISCOVERY_STATUS_COMPLETED else ""
    warnings = [str(item) for item in discovery_payload.get("warnings") or [] if str(item).strip()]
    return PeopleDiscoveryRun(
        run_id=run_id,
        workspace_id=workspace_id,
        job_id=str(job.job_id or ""),
        company=str(job.company or ""),
        job_title=str(job.title or ""),
        people_discovery_status=discovery_status,
        context_extraction=context,
        search_hypotheses=hypotheses,
        public_profile_candidates=public_profile_candidates,
        categories=categories,
        passes=list(discovery_payload.get("passes") or []),
        provider=dict(discovery_payload.get("provider") or {}),
        warnings=_user_visible_discovery_warnings(warnings),
        error=discovery_error,
        last_started_at=last_started_at,
        last_completed_at=completed_at,
        last_updated_at=utc_now_iso(),
    ).to_dict()


def _status_for_discovery_payload(discovery_payload: dict[str, Any]) -> tuple[str, str]:
    provider = dict(discovery_payload.get("provider") or {})
    warnings = [
        str(item).strip()
        for item in discovery_payload.get("warnings") or []
        if str(item).strip()
    ]
    if str(provider.get("search") or "") == "offline_fallback" or any(
        "live networking discovery is disabled" in warning for warning in warnings
    ):
        return PEOPLE_DISCOVERY_STATUS_NOT_CONFIGURED, LIVE_DISCOVERY_NOT_CONFIGURED_ERROR
    if _public_profile_search_failed_before_results(
        discovery_payload=discovery_payload,
        warnings=warnings,
    ):
        return PEOPLE_DISCOVERY_STATUS_FAILED, LIVE_DISCOVERY_SEARCH_FAILED_ERROR
    return PEOPLE_DISCOVERY_STATUS_COMPLETED, ""


def _public_profile_search_failed_before_results(
    *,
    discovery_payload: dict[str, Any],
    warnings: list[str],
) -> bool:
    if not any(warning.startswith("search_failed_pass_") for warning in warnings):
        return False
    provider = dict(discovery_payload.get("provider") or {})
    if str(provider.get("search") or "") == "offline_fallback":
        return False
    result_count = 0
    for raw_pass in discovery_payload.get("passes") or []:
        if not isinstance(raw_pass, dict):
            continue
        try:
            result_count += int(raw_pass.get("result_count") or 0)
        except (TypeError, ValueError):
            continue
    return result_count == 0


def _user_visible_discovery_warnings(warnings: list[str]) -> list[str]:
    visible: list[str] = []
    for warning in warnings:
        normalized = str(warning or "").strip()
        if not normalized:
            continue
        if normalized.startswith("search_failed_pass_"):
            visible.append(normalized)
    return visible


def update_relevant_people_status(
    discovery_run: dict[str, Any],
    *,
    person_id: str,
    status: str,
) -> dict[str, Any]:
    normalized_run = normalize_relevant_people_discovery_run(discovery_run)
    updated = False
    for category in PEOPLE_CATEGORIES:
        for person in normalized_run["categories"].get(category, []):
            if str(person.get("id") or "") == str(person_id or ""):
                person["status"] = status
                updated = True
                break
        if updated:
            break
    if not updated:
        raise KeyError(f"Relevant person '{person_id}' not found.")
    normalized_run["selectedPeople"] = _selected_people_from_categories(
        normalized_run.get("categories") or {}
    )
    normalized_run["lastUpdatedAt"] = utc_now_iso()
    return normalized_run


def normalize_relevant_people_discovery_run(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    payload.setdefault("runId", "")
    payload.setdefault("workspaceId", "")
    payload.setdefault("jobId", "")
    payload.setdefault("company", "")
    payload.setdefault("jobTitle", "")
    payload.setdefault("peopleDiscoveryStatus", PEOPLE_DISCOVERY_STATUS_NOT_STARTED)
    payload.setdefault("contextExtraction", {})
    payload.setdefault("searchHypotheses", [])
    payload.setdefault("publicProfileCandidates", [])
    payload.setdefault("passes", [])
    payload.setdefault("provider", {})
    payload.setdefault("warnings", [])
    payload.setdefault("error", "")
    payload.setdefault("lastStartedAt", "")
    payload.setdefault("lastCompletedAt", "")
    payload.setdefault("lastUpdatedAt", utc_now_iso())
    categories = dict(payload.get("categories") or {})
    for category in PEOPLE_CATEGORIES:
        categories.setdefault(category, [])
    payload["categories"] = categories
    payload["selectedPeople"] = _selected_people_from_categories(categories)
    return payload


def _selected_people_from_categories(
    categories: dict[str, list[dict[str, Any]]] | None,
) -> list[dict[str, Any]]:
    selected_people: list[dict[str, Any]] = []
    for category in PEOPLE_CATEGORIES:
        for person in categories.get(category, []) if isinstance(categories, dict) else []:
            if not isinstance(person, dict):
                continue
            if str(person.get("status") or "") not in {"confirmed", "saved_for_outreach"}:
                continue
            selected_people.append(dict(person))
    return selected_people


def _build_context_extraction(
    *,
    job: JobRecord,
    discovery_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    discipline_key = str(
        (discovery_payload or {}).get("discipline")
        or _infer_target_contact_discipline(job)
        or "general"
    ).strip()
    discipline = _TARGET_DISCIPLINE_LIBRARY.get(discipline_key, _TARGET_DISCIPLINE_LIBRARY["general"])
    location_hint = str(
        (discovery_payload or {}).get("location_hint")
        or _target_contact_location_hint(job.location_raw)
        or ""
    ).strip()
    return {
        "company": str(job.company or ""),
        "jobTitle": str(job.title or ""),
        "location": str(job.location_raw or ""),
        "locationHint": location_hint,
        "department": str((discovery_payload or {}).get("department_label") or discipline.get("label") or "Hiring Team"),
        "discipline": discipline_key,
        "seniority": _infer_job_seniority(job),
        "businessUnit": _extract_business_unit(job),
        "keywords": _extract_keywords(job),
        "descriptionExcerpt": _compact_text(str(job.description_text or ""), limit=460),
    }


def _build_search_hypotheses(
    *,
    job: JobRecord,
    discovery_payload: dict[str, Any],
    context: dict[str, Any],
) -> list[SearchHypothesis]:
    hypotheses: list[SearchHypothesis] = []
    keywords = [str(item) for item in context.get("keywords") or [] if str(item).strip()]
    location_modifiers = [
        item
        for item in (
            str(context.get("locationHint") or "").strip(),
            str(context.get("businessUnit") or "").strip(),
        )
        if item
    ]
    for pass_payload in discovery_payload.get("passes") or []:
        pass_index = int(pass_payload.get("pass_index") or 0)
        for query_index, query_plan in enumerate(pass_payload.get("queries") or [], start=1):
            lane = str(query_plan.get("lane") or "").strip()
            category = _FINAL_CATEGORY_BY_LANE.get(lane)
            if not category:
                continue
            title_variants = [str(item).strip() for item in query_plan.get("title_variants") or [] if str(item).strip()]
            explanation = str(query_plan.get("rationale") or query_plan.get("objective") or "").strip()
            hypotheses.append(
                SearchHypothesis(
                    hypothesis_id=f"hypothesis_{pass_index}_{query_index}_{category}",
                    pass_index=pass_index,
                    category=category,
                    title_query=title_variants[0] if title_variants else str(job.title or ""),
                    keyword_query=", ".join(keywords[:4]),
                    location_modifiers=location_modifiers,
                    confidence_before_search=_baseline_hypothesis_confidence(category=category, pass_index=pass_index),
                    explanation=explanation,
                    discovered_query=str(query_plan.get("query") or "").strip(),
                    lane=lane,
                )
            )
    return hypotheses


def _build_public_profile_candidates(
    *,
    discovery_payload: dict[str, Any],
    hypotheses: list[SearchHypothesis],
) -> list[PublicProfileCandidate]:
    query_by_pass_and_lane = {
        (item.pass_index, item.lane): item.discovered_query
        for item in hypotheses
        if item.lane
    }
    candidates: list[PublicProfileCandidate] = []
    for pass_payload in discovery_payload.get("passes") or []:
        pass_index = int(pass_payload.get("pass_index") or 0)
        for result_index, result in enumerate(pass_payload.get("results_preview") or [], start=1):
            profile_url = str(result.get("url") or "").strip()
            if not _is_public_person_profile_url(profile_url):
                continue
            lane = str(result.get("lane") or "").strip()
            category = _FINAL_CATEGORY_BY_LANE.get(lane)
            if not category:
                continue
            parsed_name, parsed_title, parsed_company = _parse_profile_result_title(str(result.get("title") or ""))
            if not parsed_name:
                continue
            candidates.append(
                PublicProfileCandidate(
                    candidate_id=f"public_profile_{pass_index}_{result_index}_{category}",
                    pass_index=pass_index,
                    category=category,
                    name=parsed_name,
                    title=parsed_title,
                    company=parsed_company,
                    location=_extract_location_from_text(str(result.get("snippet") or "")),
                    profile_url=profile_url,
                    source=str(result.get("source_domain") or "public_profile_search").strip(),
                    search_query=query_by_pass_and_lane.get((pass_index, lane), ""),
                    evidence_snippets=[
                        item
                        for item in (
                            str(result.get("title") or "").strip(),
                            _compact_text(str(result.get("snippet") or ""), limit=180),
                        )
                        if item
                    ],
                    match_summary=_compact_text(str(result.get("snippet") or ""), limit=220),
                    lane=lane,
                )
            )
    return candidates


def _build_relevant_people_categories(
    *,
    job: JobRecord,
    discovery_payload: dict[str, Any],
    context: dict[str, Any],
    public_profile_candidates: list[PublicProfileCandidate],
) -> dict[str, list[RelevantPerson]]:
    categories: dict[str, list[RelevantPerson]] = {category: [] for category in PEOPLE_CATEGORIES}
    seen_keys: set[str] = set()

    for raw_candidate in discovery_payload.get("candidates") or []:
        category = _FINAL_CATEGORY_BY_LANE.get(str(raw_candidate.get("lane") or "").strip())
        if not category:
            continue
        person = _build_relevant_person_from_discovery_candidate(
            job=job,
            context=context,
            raw_candidate=raw_candidate,
            category=category,
        )
        if person is None:
            continue
        dedupe_key = _relevant_person_dedupe_key(person)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        categories[category].append(person)

    grouped_profile_candidates: dict[str, list[PublicProfileCandidate]] = {category: [] for category in PEOPLE_CATEGORIES}
    for candidate in public_profile_candidates:
        grouped_profile_candidates.setdefault(candidate.category, []).append(candidate)

    for category in PEOPLE_CATEGORIES:
        for raw_candidate in grouped_profile_candidates.get(category, []):
            if len(categories[category]) >= 2:
                break
            person = _build_relevant_person_from_profile_candidate(
                job=job,
                context=context,
                raw_candidate=raw_candidate,
                category=category,
            )
            if person is None:
                continue
            dedupe_key = _relevant_person_dedupe_key(person)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            categories[category].append(person)

    for category in PEOPLE_CATEGORIES:
        categories[category].sort(
            key=lambda person: (
                -int(person.confidence or 0),
                0 if person.profile_url else 1,
                str(person.name or "").casefold(),
            )
        )
        categories[category] = categories[category][:2]
    return categories


def _build_relevant_person_from_discovery_candidate(
    *,
    job: JobRecord,
    context: dict[str, Any],
    raw_candidate: dict[str, Any],
    category: str,
) -> RelevantPerson | None:
    name = str(raw_candidate.get("resolved_name") or raw_candidate.get("guessed_name") or "").strip()
    profile_url = _first_person_profile_url(raw_candidate.get("source_urls") or [])
    if not name or not profile_url or not _looks_like_person_name(name):
        return None
    title = str(raw_candidate.get("current_title") or raw_candidate.get("resolved_title") or "").strip()
    company = str(raw_candidate.get("current_company") or raw_candidate.get("resolved_company") or job.company or "").strip()
    location = str(raw_candidate.get("location") or raw_candidate.get("resolved_location") or "").strip()
    evidence = [
        str(item).strip()
        for item in [
            *(raw_candidate.get("evidence") or []),
            *(raw_candidate.get("source_titles") or []),
        ]
        if str(item).strip()
    ]
    search_query = str(raw_candidate.get("search_query") or "").strip()
    breakdown = _build_confidence_breakdown(
        job=job,
        context=context,
        category=category,
        title=title,
        company=company,
        location=location,
        evidence=evidence,
        profile_url=profile_url,
    )
    caveats = _build_caveats(job=job, title=title, location=location, evidence=evidence)
    reasoning_note = _build_reasoning_note(
        category=category,
        title=title,
        company=company,
        job=job,
        caveats=caveats,
        evidence=evidence,
    )
    return RelevantPerson(
        person_id=f"person_{category}_{_slug(name)}",
        category=category,
        name=name,
        title=title,
        company=company,
        location=location,
        profile_url=profile_url,
        source="public_profile_search",
        confidence=breakdown.total,
        confidence_label=breakdown.label,
        reasoning_note=reasoning_note,
        evidence_snippets=evidence[:4],
        caveats=caveats,
        search_queries=[query for query in [search_query] if query],
        discovered_search_query=search_query,
        region_scope_caveat=caveats[0] if caveats else "",
        confidence_breakdown=breakdown,
        status="unreviewed",
    )


def _build_relevant_person_from_profile_candidate(
    *,
    job: JobRecord,
    context: dict[str, Any],
    raw_candidate: PublicProfileCandidate,
    category: str,
) -> RelevantPerson | None:
    if (
        not raw_candidate.name
        or not raw_candidate.profile_url
        or not _is_public_person_profile_url(raw_candidate.profile_url)
        or not _looks_like_person_name(raw_candidate.name)
    ):
        return None
    evidence = [str(item).strip() for item in raw_candidate.evidence_snippets if str(item).strip()]
    breakdown = _build_confidence_breakdown(
        job=job,
        context=context,
        category=category,
        title=raw_candidate.title,
        company=raw_candidate.company or job.company,
        location=raw_candidate.location,
        evidence=evidence,
        profile_url=raw_candidate.profile_url,
    )
    caveats = _build_caveats(
        job=job,
        title=raw_candidate.title,
        location=raw_candidate.location,
        evidence=evidence,
    )
    reasoning_note = _build_reasoning_note(
        category=category,
        title=raw_candidate.title,
        company=raw_candidate.company or job.company,
        job=job,
        caveats=caveats,
        evidence=evidence,
    )
    return RelevantPerson(
        person_id=f"person_{category}_{_slug(raw_candidate.name)}",
        category=category,
        name=raw_candidate.name,
        title=raw_candidate.title,
        company=raw_candidate.company or job.company,
        location=raw_candidate.location,
        profile_url=raw_candidate.profile_url,
        source=raw_candidate.source or "public_profile_search",
        confidence=max(35, min(92, breakdown.total - 5)),
        confidence_label=_confidence_label_for_score(max(35, min(92, breakdown.total - 5))),
        reasoning_note=reasoning_note,
        evidence_snippets=evidence[:4],
        caveats=caveats,
        search_queries=[query for query in [raw_candidate.search_query] if query],
        discovered_search_query=raw_candidate.search_query,
        region_scope_caveat=caveats[0] if caveats else "",
        confidence_breakdown=ConfidenceBreakdown(
            company_match=breakdown.company_match,
            title_category_match=breakdown.title_category_match,
            department_function_match=breakdown.department_function_match,
            location_region_match=breakdown.location_region_match,
            seniority_fit=breakdown.seniority_fit,
            business_unit_relevance=breakdown.business_unit_relevance,
            profile_freshness=breakdown.profile_freshness,
            source_reliability=breakdown.source_reliability,
            evidence_quality=breakdown.evidence_quality,
            total=max(35, min(92, breakdown.total - 5)),
            label=_confidence_label_for_score(max(35, min(92, breakdown.total - 5))),
        ),
        status="unreviewed",
    )


def _build_confidence_breakdown(
    *,
    job: JobRecord,
    context: dict[str, Any],
    category: str,
    title: str,
    company: str,
    location: str,
    evidence: list[str],
    profile_url: str,
) -> ConfidenceBreakdown:
    company_match = 100 if company_names_safely_match(company, job.company) else (55 if not company else 18)
    title_category_match = _title_match_score(category=category, title=title)
    department_function_match = _department_match_score(
        title=title,
        evidence=evidence,
        context=context,
        category=category,
    )
    location_region_match = _location_match_score(job_location=job.location_raw, candidate_location=location, title=title)
    seniority_fit = _seniority_fit_score(category=category, title=title)
    business_unit_relevance = _business_unit_score(
        title=title,
        evidence=evidence,
        business_unit=str(context.get("businessUnit") or ""),
    )
    profile_freshness = 50
    source_reliability = _source_reliability_score(profile_url)
    evidence_quality = _evidence_quality_score(evidence=evidence, title=title, location=location)

    weights = {
        "company": 24,
        "title": 20,
        "department": 16,
        "location": 14,
        "seniority": 10,
        "business_unit": 6,
        "freshness": 4,
        "source": 3,
        "evidence": 3,
    }
    total = round(
        (
            company_match * weights["company"]
            + title_category_match * weights["title"]
            + department_function_match * weights["department"]
            + location_region_match * weights["location"]
            + seniority_fit * weights["seniority"]
            + business_unit_relevance * weights["business_unit"]
            + profile_freshness * weights["freshness"]
            + source_reliability * weights["source"]
            + evidence_quality * weights["evidence"]
        )
        / sum(weights.values())
    )
    total = max(0, min(100, int(total)))
    return ConfidenceBreakdown(
        company_match=company_match,
        title_category_match=title_category_match,
        department_function_match=department_function_match,
        location_region_match=location_region_match,
        seniority_fit=seniority_fit,
        business_unit_relevance=business_unit_relevance,
        profile_freshness=profile_freshness,
        source_reliability=source_reliability,
        evidence_quality=evidence_quality,
        total=total,
        label=_confidence_label_for_score(total),
    )


def _baseline_hypothesis_confidence(*, category: str, pass_index: int) -> int:
    base = {
        PEOPLE_CATEGORY_HIRING_MANAGER: 74,
        PEOPLE_CATEGORY_POTENTIAL_COLLEAGUE: 66,
        PEOPLE_CATEGORY_EXECUTIVE: 70,
    }.get(category, 60)
    return max(35, min(90, base - (5 if pass_index > 1 else 0)))


def _build_reasoning_note(
    *,
    category: str,
    title: str,
    company: str,
    job: JobRecord,
    caveats: list[str],
    evidence: list[str],
) -> str:
    category_label = PEOPLE_CATEGORY_LABELS.get(category, "Potential match")
    base = (
        f"Likely relevant because this person appears to be a {title or category_label.lower()} "
        f"at {company or job.company or 'the target company'}."
    )
    if evidence:
        base += " Confidence is based on public profile signals."
    if caveats:
        base += f" {caveats[0]}"
    return _compact_text(base, limit=260)


def _build_caveats(
    *,
    job: JobRecord,
    title: str,
    location: str,
    evidence: list[str],
) -> list[str]:
    caveats: list[str] = []
    combined = " ".join([title, location, *evidence])
    if _REGIONAL_SCOPE_PATTERN.search(combined):
        caveats.append(
            "Their remit may be broader than the exact team or country for this role."
        )
    job_location = str(job.location_raw or "").strip()
    candidate_location = str(location or "").strip()
    if job_location and candidate_location and not _shares_location_signal(job_location, candidate_location):
        caveats.append(
            "The visible location signal may point to a different city or region than the selected job."
        )
    if not candidate_location:
        caveats.append("Public results did not clearly confirm the candidate's current location.")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in caveats:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:2]


def _title_match_score(*, category: str, title: str) -> int:
    normalized = str(title or "").casefold()
    if not normalized:
        return 42
    keywords = _TITLE_KEYWORDS_BY_CATEGORY.get(category, ())
    if any(keyword in normalized for keyword in keywords):
        return 92
    if category == PEOPLE_CATEGORY_HIRING_MANAGER and "recruit" in normalized:
        return 35
    return 55


def _department_match_score(
    *,
    title: str,
    evidence: list[str],
    context: dict[str, Any],
    category: str,
) -> int:
    discipline = str(context.get("discipline") or "").replace("_", " ").strip()
    department = str(context.get("department") or "").strip()
    keywords = [discipline.casefold(), department.casefold(), *[str(item).casefold() for item in context.get("keywords") or []]]
    searchable = " ".join([title, *evidence]).casefold()
    matched = [keyword for keyword in keywords if keyword and keyword in searchable]
    if matched:
        return 88
    if category == PEOPLE_CATEGORY_EXECUTIVE and department:
        return 68
    return 48 if searchable else 40


def _location_match_score(*, job_location: str, candidate_location: str, title: str) -> int:
    if not candidate_location:
        return 52
    if _shares_location_signal(job_location, candidate_location):
        return 88
    if _REGIONAL_SCOPE_PATTERN.search(" ".join([title, candidate_location])):
        return 58
    return 34


def _seniority_fit_score(*, category: str, title: str) -> int:
    normalized = str(title or "").casefold()
    if not normalized:
        return 46
    if category == PEOPLE_CATEGORY_EXECUTIVE:
        return 92 if any(keyword in normalized for keyword in (*_SENIORITY_KEYWORDS["executive"], *_SENIORITY_KEYWORDS["director"])) else 40
    if category == PEOPLE_CATEGORY_HIRING_MANAGER:
        if any(keyword in normalized for keyword in _SENIORITY_KEYWORDS["manager"]):
            return 88
        if any(keyword in normalized for keyword in (*_SENIORITY_KEYWORDS["executive"], *_SENIORITY_KEYWORDS["director"])):
            return 72
        return 40
    if any(keyword in normalized for keyword in _SENIORITY_KEYWORDS["individual_contributor"]):
        return 86
    if any(keyword in normalized for keyword in _SENIORITY_KEYWORDS["manager"]):
        return 60
    return 42


def _business_unit_score(*, title: str, evidence: list[str], business_unit: str) -> int:
    searchable = " ".join([title, *evidence]).casefold()
    if business_unit and business_unit.casefold() in searchable:
        return 86
    return 55 if searchable else 45


def _source_reliability_score(profile_url: str) -> int:
    lowered = str(profile_url or "").casefold()
    if "linkedin.com/in/" in lowered:
        return 84
    if lowered.startswith("https://") or lowered.startswith("http://"):
        return 68
    return 48


def _evidence_quality_score(*, evidence: list[str], title: str, location: str) -> int:
    if len(evidence) >= 3 and title and location:
        return 84
    if len(evidence) >= 2 and title:
        return 72
    if evidence:
        return 60
    return 42


def _confidence_label_for_score(score: int) -> str:
    for threshold, label in _CONFIDENCE_LABELS:
        if int(score) >= threshold:
            return label
    return "Low"


def _parse_profile_result_title(title: str) -> tuple[str, str, str]:
    cleaned = str(title or "").replace("| LinkedIn", "").strip(" -|")
    parts = [part.strip() for part in cleaned.split(" - ") if part.strip()]
    if len(parts) >= 3 and _looks_like_person_name(parts[0]):
        return parts[0], parts[1], parts[2]
    if len(parts) >= 2 and _looks_like_person_name(parts[0]):
        return parts[0], parts[1], ""
    return "", "", ""


def _extract_location_from_text(text: str) -> str:
    parts = [part.strip() for part in re.split("[|,;\u00b7]", str(text or "")) if part.strip()]
    for part in parts:
        lowered = part.casefold()
        if any(token in lowered for token in ("ausbildung", "education", "university", "school")):
            continue
        if any(token in lowered for token in ("ort:", "location:", "located in", "standort")):
            return _compact_text(part, limit=90)
        if any(token in lowered for token in ("berlin", "munich", "hamburg", "remote")) and len(part.split()) <= 6:
            return _compact_text(part, limit=90)
    return ""


def _extract_business_unit(job: JobRecord) -> str:
    extra_fields = dict(job.extra_fields or {})
    for key in ("business_unit", "businessUnit", "department", "team", "organization", "org"):
        value = str(extra_fields.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_keywords(job: JobRecord, *, limit: int = 8) -> list[str]:
    extra_fields = dict(job.extra_fields or {})
    raw_keywords = extra_fields.get("keywords") or extra_fields.get("keyword_list") or []
    keywords: list[str] = []
    if isinstance(raw_keywords, str):
        raw_keywords = re.split(r"[,;\n]+", raw_keywords)
    for item in raw_keywords if isinstance(raw_keywords, list) else []:
        normalized = str(item or "").strip()
        if normalized:
            keywords.append(normalized)
    text_sources = [str(job.title or ""), str(job.role_category_name or ""), str(job.description_text or "")]
    seen = {item.casefold() for item in keywords}
    for source in text_sources:
        for token in _WORD_PATTERN.findall(source):
            normalized = token.strip()
            lowered = normalized.casefold()
            if len(normalized) < 4 or lowered in _KEYWORD_STOPWORDS or lowered in seen:
                continue
            seen.add(lowered)
            keywords.append(normalized)
            if len(keywords) >= limit:
                return keywords[:limit]
    return keywords[:limit]


def _infer_job_seniority(job: JobRecord) -> str:
    extra_fields = dict(job.extra_fields or {})
    for key in ("seniority", "seniority_level", "experience_level"):
        value = str(extra_fields.get(key) or "").strip()
        if value:
            return value
    normalized = str(job.title or "").casefold()
    if any(keyword in normalized for keyword in _SENIORITY_KEYWORDS["executive"]):
        return "executive"
    if any(keyword in normalized for keyword in _SENIORITY_KEYWORDS["director"]):
        return "director"
    if any(keyword in normalized for keyword in _SENIORITY_KEYWORDS["manager"]):
        return "manager"
    if "senior" in normalized:
        return "senior_individual_contributor"
    return "individual_contributor"


def _relevant_person_dedupe_key(person: RelevantPerson) -> str:
    return "|".join(
        [
            str(person.category or ""),
            str(person.profile_url or "").casefold(),
            _slug(person.name),
            _slug(person.company),
        ]
    )


def _shares_location_signal(left: str, right: str) -> bool:
    left_tokens = {_slug(token) for token in re.split(r"[,/|-]", str(left or "")) if _slug(token)}
    right_tokens = {_slug(token) for token in re.split(r"[,/|-]", str(right or "")) if _slug(token)}
    return bool(left_tokens and right_tokens and left_tokens.intersection(right_tokens))


def _looks_like_person_name(value: str) -> bool:
    parts = [part for part in str(value or "").strip().split() if part]
    if len(parts) < 2 or len(parts) > 4:
        return False
    lowered = {part.casefold().strip(".,") for part in parts}
    if lowered.intersection(_PERSON_SUFFIX_BLOCKLIST):
        return False
    alpha_parts = [part for part in parts if re.search(r"[A-Za-z]", part)]
    return len(alpha_parts) >= 2


def _compact_text(value: str, *, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}…"


def _first_non_empty(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_person_profile_url(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if _is_public_person_profile_url(text):
            return text
    return ""


def _is_public_person_profile_url(value: str) -> bool:
    lowered = str(value or "").strip().casefold()
    return "linkedin.com/in/" in lowered or "xing.com/profile/" in lowered


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")[:80] or "item"
