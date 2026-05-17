from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from backend.config.job_seeker import load_project_dotenv
from backend.domain.models import JobRecord

from .outreach import (
    TargetContactCandidate,
    _NON_ALNUM,
    _TARGET_CONTACT_BLUEPRINTS,
    _TARGET_DISCIPLINE_LIBRARY,
    _build_target_connection_note,
    _build_target_contact_google_query,
    _build_target_contact_search_query,
    _build_target_follow_up_message,
    _infer_target_contact_discipline,
    _job_summary,
    _target_contact_location_hint,
    guess_hiring_manager_from_job,
)


_DISCOVERY_SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_DISCOVERY_AI_SYSTEM_PROMPT = (
    "You plan and resolve job-networking contact discovery from public evidence. "
    "Return valid JSON only. Never invent people, teams, locations, or certainty beyond the evidence."
)
_DISCOVERY_STOPWORDS = {
    "about",
    "across",
    "after",
    "all",
    "also",
    "and",
    "application",
    "apply",
    "applying",
    "at",
    "based",
    "between",
    "build",
    "business",
    "candidate",
    "company",
    "country",
    "customers",
    "data",
    "department",
    "different",
    "drive",
    "experience",
    "focus",
    "for",
    "from",
    "full",
    "global",
    "gmbh",
    "group",
    "have",
    "help",
    "hiring",
    "into",
    "job",
    "jobs",
    "lead",
    "level",
    "location",
    "manager",
    "more",
    "need",
    "network",
    "operations",
    "or",
    "our",
    "owner",
    "people",
    "product",
    "program",
    "project",
    "recruiter",
    "role",
    "same",
    "search",
    "senior",
    "site",
    "software",
    "team",
    "that",
    "the",
    "their",
    "them",
    "there",
    "this",
    "through",
    "title",
    "use",
    "using",
    "with",
    "work",
    "working",
    "your",
}
_CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}
_LANE_TO_TITLE_KEY = {
    "direct_hiring_chain": "manager_titles",
    "recruiting": "recruiter_titles",
    "leadership": "leader_titles",
    "peer_context": "peer_titles",
}

_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_BLUEPRINT_BY_LANE = {
    str(item["lane"]): item
    for item in _TARGET_CONTACT_BLUEPRINTS
}


@dataclass(slots=True)
class DiscoveryQueryPlan:
    pass_index: int
    query: str
    objective: str = ""
    lane: str = ""
    rationale: str = ""
    title_variants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_index": self.pass_index,
            "query": self.query,
            "objective": self.objective,
            "lane": self.lane,
            "rationale": self.rationale,
            "title_variants": list(self.title_variants),
        }


@dataclass(slots=True)
class DiscoverySearchHit:
    pass_index: int
    query: str
    title: str
    url: str
    snippet: str = ""
    source_domain: str = ""
    rank: int = 0
    lane: str = ""
    objective: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_index": self.pass_index,
            "query": self.query,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_domain": self.source_domain,
            "rank": self.rank,
            "lane": self.lane,
            "objective": self.objective,
        }

    def prompt_line(self) -> str:
        snippet = _truncate_text(self.snippet, limit=200)
        return (
            f"[P{self.pass_index} #{self.rank}] lane={self.lane or 'general'} "
            f"| domain={self.source_domain or 'unknown'} | title={self.title} "
            f"| snippet={snippet} | url={self.url}"
        )


def build_target_contact_discovery(
    *,
    profile: dict[str, Any],
    job: JobRecord,
    search_provider: Callable[..., list[dict[str, Any]] | list[DiscoverySearchHit]] | None = None,
    ai_provider: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    live_discovery_enabled = _live_target_contact_discovery_enabled()
    effective_search_provider = (
        search_provider
        if search_provider is not None
        else (None if live_discovery_enabled else _offline_search_provider)
    )
    effective_ai_provider = (
        ai_provider
        if ai_provider is not None
        else (None if live_discovery_enabled else _disabled_ai_provider)
    )
    discipline_key = _infer_target_contact_discipline(job)
    discipline = _TARGET_DISCIPLINE_LIBRARY.get(discipline_key, _TARGET_DISCIPLINE_LIBRARY["general"])
    discipline_label = str(discipline.get("label") or "Hiring Team").strip() or "Hiring Team"
    company = str(job.company or "").strip()
    location_hint = _target_contact_location_hint(job.location_raw)
    hiring_manager = guess_hiring_manager_from_job(job)
    warnings: list[str] = []
    provider = {
        "search": (
            "custom"
            if search_provider is not None
            else ("duckduckgo_html" if live_discovery_enabled else "offline_fallback")
        ),
        "query_planner": "heuristic_fallback",
        "resolver": "heuristic_fallback",
    }

    pass_one_queries = _build_pass_one_query_plans(
        job=job,
        discipline_key=discipline_key,
        discipline=discipline,
        location_hint=location_hint,
        hiring_manager=hiring_manager,
        ai_provider=effective_ai_provider,
        warnings=warnings,
        provider=provider,
    )
    pass_one_hits = _search_for_pass_queries(
        pass_one_queries,
        search_provider=effective_search_provider,
        warnings=warnings,
    )

    pass_two_queries = _build_pass_two_query_plans(
        job=job,
        discipline_key=discipline_key,
        discipline=discipline,
        location_hint=location_hint,
        hiring_manager=hiring_manager,
        pass_one_queries=pass_one_queries,
        pass_one_hits=pass_one_hits,
        ai_provider=effective_ai_provider,
        warnings=warnings,
        provider=provider,
    )
    pass_two_hits = _search_for_pass_queries(
        pass_two_queries,
        search_provider=effective_search_provider,
        warnings=warnings,
    )

    combined_hits = _dedupe_hits([*pass_one_hits, *pass_two_hits])
    candidates = _resolve_candidates(
        profile=profile,
        job=job,
        discipline_key=discipline_key,
        discipline=discipline,
        discipline_label=discipline_label,
        hiring_manager=hiring_manager,
        pass_one_queries=pass_one_queries,
        pass_two_queries=pass_two_queries,
        pass_one_hits=pass_one_hits,
        pass_two_hits=pass_two_hits,
        combined_hits=combined_hits,
        ai_provider=effective_ai_provider,
        warnings=warnings,
        provider=provider,
    )

    strategy_bits = [
        f"Two-pass discovery is the default for the {discipline_label} lane.",
        "Pass 1 explores likely manager, recruiter, leadership, and peer lanes from public web results.",
        "Pass 2 always refines using what pass 1 surfaced so the search can narrow away from wrong-country, generic HR, or unrelated team hits.",
    ]
    if company:
        strategy_bits.append(f"Company anchor: {company}.")
    if location_hint:
        strategy_bits.append(f"Location hint: {location_hint}.")
    strategy_bits.append("Only evidence-backed people should be treated as named candidates; everything else stays a narrower search lane.")

    return {
        "job": _job_summary(job),
        "discipline": discipline_key,
        "department_label": discipline_label,
        "location_hint": location_hint,
        "default_pass_count": 2,
        "strategy_summary": " ".join(strategy_bits),
        "hiring_manager_signal": hiring_manager.to_dict(),
        "provider": provider,
        "warnings": warnings,
        "passes": [
            _pass_payload(
                pass_index=1,
                summary="Initial discovery across public manager, recruiter, leadership, and team-insider lanes.",
                queries=pass_one_queries,
                hits=pass_one_hits,
            ),
            _pass_payload(
                pass_index=2,
                summary="Mandatory refinement pass using what pass 1 exposed to tighten location, business-unit, and responsibility fit.",
                queries=pass_two_queries,
                hits=pass_two_hits,
            ),
        ],
        "resolution_summary": _build_resolution_summary(candidates),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }


def _build_pass_one_query_plans(
    *,
    job: JobRecord,
    discipline_key: str,
    discipline: dict[str, Any],
    location_hint: str,
    hiring_manager,
    ai_provider: Callable[..., dict[str, Any]] | None,
    warnings: list[str],
    provider: dict[str, str],
) -> list[DiscoveryQueryPlan]:
    prompt = _pass_one_prompt(
        job=job,
        discipline_key=discipline_key,
        discipline=discipline,
        location_hint=location_hint,
        hiring_manager=hiring_manager,
    )
    try:
        payload = _call_discovery_ai(
            task="pass_one_queries",
            prompt=prompt,
            system_prompt=_DISCOVERY_AI_SYSTEM_PROMPT,
            ai_provider=ai_provider,
        )
        plans = _coerce_query_plans(payload, pass_index=1, discipline=discipline)
        if plans:
            provider["query_planner"] = "ai"
            return plans
        warnings.append("pass1_ai_empty_query_plan")
    except Exception as exc:
        warnings.append(f"pass1_query_planner_failed:{_compact_whitespace(str(exc))}")
    return _heuristic_pass_one_queries(
        job=job,
        discipline=discipline,
        location_hint=location_hint,
        hiring_manager=hiring_manager,
    )


def _build_pass_two_query_plans(
    *,
    job: JobRecord,
    discipline_key: str,
    discipline: dict[str, Any],
    location_hint: str,
    hiring_manager,
    pass_one_queries: list[DiscoveryQueryPlan],
    pass_one_hits: list[DiscoverySearchHit],
    ai_provider: Callable[..., dict[str, Any]] | None,
    warnings: list[str],
    provider: dict[str, str],
) -> list[DiscoveryQueryPlan]:
    prompt = _pass_two_prompt(
        job=job,
        discipline_key=discipline_key,
        discipline=discipline,
        location_hint=location_hint,
        hiring_manager=hiring_manager,
        pass_one_queries=pass_one_queries,
        pass_one_hits=pass_one_hits,
    )
    try:
        payload = _call_discovery_ai(
            task="pass_two_queries",
            prompt=prompt,
            system_prompt=_DISCOVERY_AI_SYSTEM_PROMPT,
            ai_provider=ai_provider,
        )
        plans = _coerce_query_plans(payload, pass_index=2, discipline=discipline)
        if plans:
            provider["query_planner"] = "ai"
            return plans
        warnings.append("pass2_ai_empty_query_plan")
    except Exception as exc:
        warnings.append(f"pass2_query_planner_failed:{_compact_whitespace(str(exc))}")
    return _heuristic_pass_two_queries(
        job=job,
        discipline=discipline,
        location_hint=location_hint,
        pass_one_queries=pass_one_queries,
        pass_one_hits=pass_one_hits,
        hiring_manager=hiring_manager,
    )


def _resolve_candidates(
    *,
    profile: dict[str, Any],
    job: JobRecord,
    discipline_key: str,
    discipline: dict[str, Any],
    discipline_label: str,
    hiring_manager,
    pass_one_queries: list[DiscoveryQueryPlan],
    pass_two_queries: list[DiscoveryQueryPlan],
    pass_one_hits: list[DiscoverySearchHit],
    pass_two_hits: list[DiscoverySearchHit],
    combined_hits: list[DiscoverySearchHit],
    ai_provider: Callable[..., dict[str, Any]] | None,
    warnings: list[str],
    provider: dict[str, str],
) -> list[TargetContactCandidate]:
    prompt = _candidate_resolution_prompt(
        job=job,
        discipline_key=discipline_key,
        discipline_label=discipline_label,
        pass_one_hits=pass_one_hits,
        pass_two_hits=pass_two_hits,
    )
    try:
        payload = _call_discovery_ai(
            task="candidate_resolution",
            prompt=prompt,
            system_prompt=_DISCOVERY_AI_SYSTEM_PROMPT,
            ai_provider=ai_provider,
        )
        candidates = _coerce_ai_candidates(
            payload=payload,
            profile=profile,
            job=job,
            discipline=discipline,
            discipline_label=discipline_label,
            hiring_manager=hiring_manager,
            all_hits=combined_hits,
        )
        if candidates:
            provider["resolver"] = "ai"
            return _supplement_with_fallback_lanes(
                existing=candidates,
                profile=profile,
                job=job,
                discipline=discipline,
                discipline_label=discipline_label,
                hiring_manager=hiring_manager,
                query_plans=pass_two_queries or pass_one_queries,
                hits=combined_hits,
            )
        warnings.append("candidate_resolver_ai_empty")
    except Exception as exc:
        warnings.append(f"candidate_resolver_failed:{_compact_whitespace(str(exc))}")
    return _fallback_candidates(
        profile=profile,
        job=job,
        discipline=discipline,
        discipline_label=discipline_label,
        hiring_manager=hiring_manager,
        query_plans=pass_two_queries or pass_one_queries,
        hits=combined_hits,
    )


def _pass_payload(
    *,
    pass_index: int,
    summary: str,
    queries: list[DiscoveryQueryPlan],
    hits: list[DiscoverySearchHit],
) -> dict[str, Any]:
    preview = hits[: min(8, len(hits))]
    return {
        "pass_index": pass_index,
        "summary": summary,
        "query_count": len(queries),
        "result_count": len(hits),
        "top_domains": _top_domains(hits),
        "queries": [query.to_dict() for query in queries],
        "results_preview": [hit.to_dict() for hit in preview],
    }


def _call_discovery_ai(
    *,
    task: str,
    prompt: str,
    system_prompt: str,
    ai_provider: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    if ai_provider is not None:
        try:
            payload = ai_provider(task=task, prompt=prompt, system_prompt=system_prompt)
        except TypeError:
            payload = ai_provider(task, prompt, system_prompt)
        if not isinstance(payload, dict):
            raise ValueError("Custom AI provider must return a JSON-like dictionary.")
        return payload
    return _call_live_deepseek_json(prompt=prompt, system_prompt=system_prompt)


def _live_target_contact_discovery_enabled() -> bool:
    load_project_dotenv()
    return str(os.getenv("RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY") or "").strip().lower() in _TRUTHY_VALUES


def _disabled_ai_provider(*_args, **_kwargs) -> dict[str, Any]:
    raise RuntimeError("live networking discovery is disabled")


def _offline_search_provider(*_args, **_kwargs) -> list[dict[str, Any]]:
    return []


def _call_live_deepseek_json(
    *,
    prompt: str,
    system_prompt: str,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    load_project_dotenv()
    api_key = str(os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing.")
    model = str(
        os.getenv("DEEPSEEK_NETWORKING_DISCOVERY_MODEL")
        or os.getenv("DEEPSEEK_STAGE4_MODEL")
        or "deepseek-chat"
    ).strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("DeepSeek response missing choices.")
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise ValueError("DeepSeek response content is empty.")
    parsed = json.loads(_strip_json_fences(content))
    if not isinstance(parsed, dict):
        raise ValueError("DeepSeek discovery response must be a JSON object.")
    return parsed


def _search_for_pass_queries(
    query_plans: list[DiscoveryQueryPlan],
    *,
    search_provider: Callable[..., list[dict[str, Any]] | list[DiscoverySearchHit]] | None,
    warnings: list[str],
    max_results_per_query: int = 5,
) -> list[DiscoverySearchHit]:
    results: list[DiscoverySearchHit] = []
    seen_urls: set[str] = set()
    for plan in query_plans:
        try:
            raw_hits = _call_search_provider(
                plan=plan,
                search_provider=search_provider,
                max_results=max_results_per_query,
            )
        except Exception as exc:
            warnings.append(
                f"search_failed_pass_{plan.pass_index}:{_compact_whitespace(str(exc))}"
            )
            continue
        for hit in raw_hits:
            canonical_url = str(hit.url or "").strip().lower()
            if canonical_url and canonical_url in seen_urls:
                continue
            if canonical_url:
                seen_urls.add(canonical_url)
            results.append(hit)
    return results


def _call_search_provider(
    *,
    plan: DiscoveryQueryPlan,
    search_provider: Callable[..., list[dict[str, Any]] | list[DiscoverySearchHit]] | None,
    max_results: int,
) -> list[DiscoverySearchHit]:
    if search_provider is None:
        raw_hits = _search_duckduckgo_html(plan.query, max_results=max_results)
    else:
        try:
            raw_hits = search_provider(
                plan.query,
                max_results=max_results,
                pass_index=plan.pass_index,
                lane=plan.lane,
                objective=plan.objective,
            )
        except TypeError:
            raw_hits = search_provider(plan.query)
    hits: list[DiscoverySearchHit] = []
    for rank, raw_hit in enumerate(raw_hits or [], start=1):
        if isinstance(raw_hit, DiscoverySearchHit):
            hits.append(
                DiscoverySearchHit(
                    pass_index=plan.pass_index,
                    query=plan.query,
                    title=raw_hit.title,
                    url=raw_hit.url,
                    snippet=raw_hit.snippet,
                    source_domain=raw_hit.source_domain,
                    rank=rank,
                    lane=plan.lane or raw_hit.lane,
                    objective=plan.objective or raw_hit.objective,
                )
            )
            continue
        if not isinstance(raw_hit, dict):
            continue
        url = str(raw_hit.get("url") or "").strip()
        title = _compact_whitespace(str(raw_hit.get("title") or ""))
        if not url or not title:
            continue
        hits.append(
            DiscoverySearchHit(
                pass_index=plan.pass_index,
                query=plan.query,
                title=title,
                url=url,
                snippet=_compact_whitespace(str(raw_hit.get("snippet") or "")),
                source_domain=_source_domain(url),
                rank=rank,
                lane=plan.lane,
                objective=plan.objective,
            )
        )
    return hits


def _search_duckduckgo_html(query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers=_DISCOVERY_SEARCH_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    nodes = soup.select(".result")
    hits: list[dict[str, Any]] = []
    for node in nodes:
        anchor = node.select_one("a.result__a") or node.select_one("a")
        if anchor is None:
            continue
        raw_url = str(anchor.get("href") or "").strip()
        url = _unwrap_search_url(raw_url)
        title = _compact_whitespace(anchor.get_text(" ", strip=True))
        if not url or not title:
            continue
        snippet_node = node.select_one(".result__snippet")
        snippet = _compact_whitespace(
            snippet_node.get_text(" ", strip=True) if snippet_node is not None else ""
        )
        hits.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )
        if len(hits) >= max_results:
            break
    return hits


def _unwrap_search_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    query = parse_qs(parsed.query or "")
    target = query.get("uddg", [""])[0]
    if target:
        return unquote(target)
    if raw.startswith("//"):
        return f"https:{raw}"
    return raw


def _pass_one_prompt(
    *,
    job: JobRecord,
    discipline_key: str,
    discipline: dict[str, Any],
    location_hint: str,
    hiring_manager,
) -> str:
    return (
        "Plan the first discovery pass for job-networking contact research.\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "summary": "string",\n'
        '  "query_plans": [\n'
        "    {\n"
        '      "query": "string",\n'
        '      "objective": "string",\n'
        '      "lane": "direct_hiring_chain|recruiting|leadership|peer_context",\n'
        '      "title_variants": ["string"],\n'
        '      "rationale": "string"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Maximum 6 queries.\n"
        "- Use public-web search queries only.\n"
        "- Include some site:linkedin.com/in x-ray queries.\n"
        "- Include company/team/business-unit queries when useful.\n"
        "- Do not invent names beyond a named signal already present in the posting.\n"
        "- Search broadly enough to discover the right lane before refinement.\n\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location hint: {location_hint or 'not specified'}\n"
        f"Discipline: {discipline_key}\n"
        f"Discipline label: {discipline.get('label') or 'Hiring Team'}\n"
        f"Hiring-manager signal: {json.dumps(hiring_manager.to_dict(), ensure_ascii=False)}\n"
        f"Description excerpt:\n{_job_description_excerpt(job)}\n"
    )


def _pass_two_prompt(
    *,
    job: JobRecord,
    discipline_key: str,
    discipline: dict[str, Any],
    location_hint: str,
    hiring_manager,
    pass_one_queries: list[DiscoveryQueryPlan],
    pass_one_hits: list[DiscoverySearchHit],
) -> str:
    return (
        "Plan the mandatory second discovery pass for the same job-networking research.\n\n"
        "Pass 2 must always run. Use what pass 1 surfaced to refine toward the correct country, city, subsidiary, site, or business unit, and away from generic HR or wrong-country matches.\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "summary": "string",\n'
        '  "query_plans": [\n'
        "    {\n"
        '      "query": "string",\n'
        '      "objective": "string",\n'
        '      "lane": "direct_hiring_chain|recruiting|leadership|peer_context",\n'
        '      "title_variants": ["string"],\n'
        '      "rationale": "string"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Maximum 6 queries.\n"
        "- Use public-web search queries only.\n"
        "- Prefer narrower queries than pass 1.\n"
        "- Do not repeat pass-1 queries verbatim unless a query is still the strongest choice.\n"
        "- Penalize global HR, group executives, and wrong-country people when the job appears local.\n\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location hint: {location_hint or 'not specified'}\n"
        f"Discipline: {discipline_key}\n"
        f"Discipline label: {discipline.get('label') or 'Hiring Team'}\n"
        f"Hiring-manager signal: {json.dumps(hiring_manager.to_dict(), ensure_ascii=False)}\n"
        "Pass 1 queries:\n"
        f"{_prompt_query_lines(pass_one_queries)}\n\n"
        "Pass 1 result previews:\n"
        f"{_prompt_hit_lines(pass_one_hits, limit=12)}\n"
    )


def _candidate_resolution_prompt(
    *,
    job: JobRecord,
    discipline_key: str,
    discipline_label: str,
    pass_one_hits: list[DiscoverySearchHit],
    pass_two_hits: list[DiscoverySearchHit],
) -> str:
    return (
        "Resolve the discovered public-web evidence into a ranked outreach shortlist.\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "summary": "string",\n'
        '  "candidates": [\n'
        "    {\n"
        '      "role_label": "string",\n'
        '      "person_name": "string",\n'
        '      "current_title": "string",\n'
        '      "current_company": "string",\n'
        '      "location": "string",\n'
        '      "seniority": "string",\n'
        '      "lane": "direct_hiring_chain|recruiting|leadership|peer_context",\n'
        '      "confidence": "high|medium|low",\n'
        '      "fit_score": 0,\n'
        '      "title_variants": ["string"],\n'
        '      "why_this_person": "string",\n'
        '      "access_hint": "string",\n'
        '      "evidence": ["string"],\n'
        '      "source_urls": ["string"],\n'
        '      "source_titles": ["string"],\n'
        '      "search_query": "string",\n'
        '      "follow_up_ask": "string"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Use only evidence from the search hits below.\n"
        "- Do not invent named people.\n"
        "- If you cannot justify a named person for a lane, leave person_name empty and keep that lane as an unresolved search target.\n"
        "- Favor same-company, same-country, same-function hits over generic executives.\n"
        "- Penalize wrong-country results even if the title looks attractive.\n"
        "- Return up to 6 candidates.\n\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Discipline: {discipline_key}\n"
        f"Department label: {discipline_label}\n"
        f"Location hint: {_target_contact_location_hint(job.location_raw) or 'not specified'}\n"
        "Pass 1 result previews:\n"
        f"{_prompt_hit_lines(pass_one_hits, limit=10)}\n\n"
        "Pass 2 result previews:\n"
        f"{_prompt_hit_lines(pass_two_hits, limit=10)}\n"
    )


def _coerce_query_plans(
    payload: dict[str, Any],
    *,
    pass_index: int,
    discipline: dict[str, Any],
) -> list[DiscoveryQueryPlan]:
    raw_items = payload.get("query_plans") or payload.get("queries") or []
    if not isinstance(raw_items, list):
        return []
    plans: list[DiscoveryQueryPlan] = []
    seen_queries: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        query = _compact_whitespace(str(raw_item.get("query") or ""))
        if not query:
            continue
        query_key = query.casefold()
        if query_key in seen_queries:
            continue
        seen_queries.add(query_key)
        lane = str(raw_item.get("lane") or "").strip() or "direct_hiring_chain"
        title_variants = _string_list(raw_item.get("title_variants"))
        if not title_variants:
            title_variants = _title_variants_for_lane(discipline=discipline, lane=lane)
        plans.append(
            DiscoveryQueryPlan(
                pass_index=pass_index,
                query=query,
                objective=_compact_whitespace(str(raw_item.get("objective") or "")),
                lane=lane,
                rationale=_compact_whitespace(str(raw_item.get("rationale") or "")),
                title_variants=title_variants,
            )
        )
    return plans[:6]


def _heuristic_pass_one_queries(
    *,
    job: JobRecord,
    discipline: dict[str, Any],
    location_hint: str,
    hiring_manager,
) -> list[DiscoveryQueryPlan]:
    company = str(job.company or "").strip()
    location = location_hint or ""
    context_terms = _job_context_terms(job)
    context_fragment = " ".join(context_terms[:2])
    plans: list[DiscoveryQueryPlan] = []
    if hiring_manager.name:
        plans.append(
            DiscoveryQueryPlan(
                pass_index=1,
                query=f'site:linkedin.com/in "{hiring_manager.name}" "{company}"',
                objective="Check whether the named hiring signal resolves to a real public profile.",
                lane="direct_hiring_chain",
                rationale="The posting already contains a named signal, so verify it first.",
                title_variants=_title_variants_for_lane(discipline=discipline, lane="direct_hiring_chain"),
            )
        )
    for lane, objective in [
        ("direct_hiring_chain", "Find the likely local manager closest to the role."),
        ("recruiting", "Find recruiter or talent-acquisition ownership for this role."),
        ("leadership", "Find a department leader in the same lane and location."),
        ("peer_context", "Find a team insider close to the same function and location."),
    ]:
        title_variants = _title_variants_for_lane(discipline=discipline, lane=lane)
        primary_title = title_variants[0] if title_variants else "Hiring Manager"
        query_bits = [f'site:linkedin.com/in "{company}"', f'"{primary_title}"']
        if location:
            query_bits.append(f'"{location}"')
        if context_fragment:
            query_bits.append(context_fragment)
        plans.append(
            DiscoveryQueryPlan(
                pass_index=1,
                query=" ".join(bit for bit in query_bits if bit),
                objective=objective,
                lane=lane,
                rationale="Heuristic broad x-ray query for the first discovery pass.",
                title_variants=title_variants,
            )
        )
    if company:
        plans.append(
            DiscoveryQueryPlan(
                pass_index=1,
                query=" ".join(
                    bit
                    for bit in [
                        f'"{company}"',
                        "team",
                        location and f'"{location}"',
                        context_fragment,
                    ]
                    if bit
                ),
                objective="Find official team, org, or business-unit pages to anchor the right subgroup.",
                lane="leadership",
                rationale="Official pages often reveal the local business unit or site name for pass 2 refinement.",
                title_variants=_title_variants_for_lane(discipline=discipline, lane="leadership"),
            )
        )
    return _dedupe_query_plans(plans)


def _heuristic_pass_two_queries(
    *,
    job: JobRecord,
    discipline: dict[str, Any],
    location_hint: str,
    pass_one_queries: list[DiscoveryQueryPlan],
    pass_one_hits: list[DiscoverySearchHit],
    hiring_manager,
) -> list[DiscoveryQueryPlan]:
    company = str(job.company or "").strip()
    location = location_hint or ""
    refinement_terms = _search_refinement_terms(job, pass_one_hits)
    term_fragment = " ".join(refinement_terms[:2])
    plans: list[DiscoveryQueryPlan] = []
    for lane, objective in [
        (
            "direct_hiring_chain",
            "Refine toward the most local manager or hiring-owner lane using pass-1 evidence.",
        ),
        (
            "recruiting",
            "Refine toward the recruiting owner closest to the role location or business unit.",
        ),
        (
            "leadership",
            "Refine toward the right department leader for the likely location or subsidiary.",
        ),
        (
            "peer_context",
            "Refine toward a team insider in the right function and geography.",
        ),
    ]:
        title_variants = _title_variants_for_lane(discipline=discipline, lane=lane)
        primary_title = title_variants[0] if title_variants else "Hiring Manager"
        query_bits = [f'site:linkedin.com/in "{company}"', f'"{primary_title}"']
        if location:
            query_bits.append(f'"{location}"')
        if term_fragment:
            query_bits.append(term_fragment)
        if hiring_manager.name and lane == "direct_hiring_chain":
            query_bits.append(f'"{hiring_manager.name}"')
        plans.append(
            DiscoveryQueryPlan(
                pass_index=2,
                query=" ".join(bit for bit in query_bits if bit),
                objective=objective,
                lane=lane,
                rationale="Second-pass heuristic query narrowed by pass-1 language and location clues.",
                title_variants=title_variants,
            )
        )
    if company and term_fragment:
        plans.append(
            DiscoveryQueryPlan(
                pass_index=2,
                query=" ".join(
                    bit
                    for bit in [
                        f'"{company}"',
                        f'"{location}"' if location else "",
                        term_fragment,
                        "hiring",
                    ]
                    if bit
                ),
                objective="Find pages that connect the role to the correct site, unit, or hiring subgroup.",
                lane="direct_hiring_chain",
                rationale="Second pass should use the discovered language to anchor the exact team or site.",
                title_variants=_title_variants_for_lane(discipline=discipline, lane="direct_hiring_chain"),
            )
        )
    # Preserve one useful pass-1 query if the first pass was sparse.
    if len(pass_one_hits) <= 2 and pass_one_queries:
        plans.append(
            DiscoveryQueryPlan(
                pass_index=2,
                query=pass_one_queries[0].query,
                objective="Re-run the strongest broad query because pass 1 returned too little evidence.",
                lane=pass_one_queries[0].lane,
                rationale="Sparse first-pass evidence is better than no evidence.",
                title_variants=list(pass_one_queries[0].title_variants),
            )
        )
    return _dedupe_query_plans(plans)


def _coerce_ai_candidates(
    *,
    payload: dict[str, Any],
    profile: dict[str, Any],
    job: JobRecord,
    discipline: dict[str, Any],
    discipline_label: str,
    hiring_manager,
    all_hits: list[DiscoverySearchHit],
) -> list[TargetContactCandidate]:
    raw_candidates = payload.get("candidates") or []
    if not isinstance(raw_candidates, list):
        return []
    hit_by_url = {str(hit.url).strip(): hit for hit in all_hits if str(hit.url).strip()}
    candidates: list[TargetContactCandidate] = []
    seen_keys: set[str] = set()
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        lane = str(raw_candidate.get("lane") or "").strip() or "direct_hiring_chain"
        role_label = _compact_whitespace(str(raw_candidate.get("role_label") or "")) or _role_label_for_lane(lane)
        person_name = _compact_whitespace(
            str(
                raw_candidate.get("person_name")
                or raw_candidate.get("name")
                or raw_candidate.get("resolved_name")
                or ""
            )
        )
        title_variants = _string_list(raw_candidate.get("title_variants"))
        if not title_variants:
            title_variants = _title_variants_for_lane(discipline=discipline, lane=lane)
        resolved_title = _compact_whitespace(
            str(raw_candidate.get("current_title") or raw_candidate.get("resolved_title") or "")
        )
        resolved_company = _compact_whitespace(
            str(raw_candidate.get("current_company") or raw_candidate.get("resolved_company") or job.company or "")
        )
        resolved_location = _compact_whitespace(
            str(raw_candidate.get("location") or raw_candidate.get("resolved_location") or "")
        )
        fit_score = _clamp_score(raw_candidate.get("fit_score"), default=_default_fit_score_for_lane(lane))
        confidence = _normalize_confidence(raw_candidate.get("confidence"))
        evidence = _string_list(raw_candidate.get("evidence"))
        source_urls = _string_list(raw_candidate.get("source_urls"))
        source_titles = _string_list(raw_candidate.get("source_titles"))
        if not source_titles and source_urls:
            source_titles = [
                hit_by_url.get(url).title
                for url in source_urls
                if hit_by_url.get(url) is not None
            ]
        if not evidence and source_urls:
            evidence = [
                _compact_whitespace(
                    " | ".join(
                        part
                        for part in [
                            hit_by_url.get(url).title if hit_by_url.get(url) is not None else "",
                            hit_by_url.get(url).snippet if hit_by_url.get(url) is not None else "",
                        ]
                        if part
                    )
                )
                for url in source_urls
                if hit_by_url.get(url) is not None
            ]
        follow_up_ask = _compact_whitespace(str(raw_candidate.get("follow_up_ask") or "")) or _default_follow_up_ask(lane)
        search_query = _compact_whitespace(str(raw_candidate.get("search_query") or ""))
        if not search_query:
            search_query = _build_target_contact_search_query(
                job=job,
                title_variants=title_variants,
                guessed_name=person_name,
            )
        google_query = _build_target_contact_google_query(
            job=job,
            title_variants=title_variants,
            guessed_name=person_name,
        )
        candidate = TargetContactCandidate(
            candidate_id=_candidate_id(role_label=role_label, person_name=person_name),
            role_label=role_label,
            title_variants=title_variants,
            fit_score=fit_score,
            confidence=confidence,
            department=discipline_label,
            seniority=_compact_whitespace(str(raw_candidate.get("seniority") or "")) or _default_seniority_for_lane(lane),
            lane=lane,
            access_hint=_compact_whitespace(str(raw_candidate.get("access_hint") or "")) or _default_access_hint(lane),
            rationale=_compact_whitespace(str(raw_candidate.get("why_this_person") or raw_candidate.get("reasoning") or "")),
            guessed_name=person_name or hiring_manager.name,
            resolved_name=person_name,
            resolved_title=resolved_title,
            resolved_company=resolved_company,
            resolved_location=resolved_location,
            search_query=search_query,
            linkedin_search_url=(
                f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(search_query)}"
                if search_query
                else ""
            ),
            google_xray_query=google_query,
            google_xray_search_url=(
                f"https://www.google.com/search?q={quote_plus(google_query)}" if google_query else ""
            ),
            evidence=evidence[:4],
            source_urls=_dedupe_strings(source_urls)[:4],
            source_titles=_dedupe_strings(source_titles)[:4],
            resolved_in_pass=_resolve_candidate_pass(source_urls, hit_by_url),
            result_type="person" if person_name else "lane",
            connection_note=_build_target_connection_note(
                job=job,
                department_label=discipline_label,
                role_label=role_label,
                name_placeholder="[Name]",
            ),
            follow_up_message=_build_target_follow_up_message(
                profile=profile,
                job=job,
                name_placeholder="[Name]",
                follow_up_ask=follow_up_ask,
            ),
        )
        dedupe_key = _candidate_dedupe_key(candidate)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            -int(item.fit_score),
            -_CONFIDENCE_ORDER.get(item.confidence, 0),
            item.role_label.casefold(),
        )
    )
    return candidates[:6]


def _supplement_with_fallback_lanes(
    *,
    existing: list[TargetContactCandidate],
    profile: dict[str, Any],
    job: JobRecord,
    discipline: dict[str, Any],
    discipline_label: str,
    hiring_manager,
    query_plans: list[DiscoveryQueryPlan],
    hits: list[DiscoverySearchHit],
) -> list[TargetContactCandidate]:
    if len(existing) >= 4:
        return existing
    supplemented = list(existing)
    fallback = _fallback_candidates(
        profile=profile,
        job=job,
        discipline=discipline,
        discipline_label=discipline_label,
        hiring_manager=hiring_manager,
        query_plans=query_plans,
        hits=hits,
    )
    seen_roles = {
        _candidate_dedupe_key(candidate)
        for candidate in supplemented
    }
    for candidate in fallback:
        key = _candidate_dedupe_key(candidate)
        if key in seen_roles:
            continue
        seen_roles.add(key)
        supplemented.append(candidate)
        if len(supplemented) >= 6:
            break
    supplemented.sort(
        key=lambda item: (
            -int(item.fit_score),
            -_CONFIDENCE_ORDER.get(item.confidence, 0),
            item.role_label.casefold(),
        )
    )
    return supplemented


def _fallback_candidates(
    *,
    profile: dict[str, Any],
    job: JobRecord,
    discipline: dict[str, Any],
    discipline_label: str,
    hiring_manager,
    query_plans: list[DiscoveryQueryPlan],
    hits: list[DiscoverySearchHit],
) -> list[TargetContactCandidate]:
    lane_to_query = {plan.lane: plan for plan in query_plans if plan.lane}
    lane_hits = _hits_by_lane(hits)
    candidates: list[TargetContactCandidate] = []

    if hiring_manager.name:
        named_plan = lane_to_query.get("direct_hiring_chain")
        title_variants = (
            list(named_plan.title_variants)
            if named_plan is not None and named_plan.title_variants
            else _title_variants_for_lane(discipline=discipline, lane="direct_hiring_chain")
        )
        search_query = _build_target_contact_search_query(
            job=job,
            title_variants=title_variants,
            guessed_name=hiring_manager.name,
        )
        google_query = _build_target_contact_google_query(
            job=job,
            title_variants=title_variants,
            guessed_name=hiring_manager.name,
        )
        supporting_hits = lane_hits.get("direct_hiring_chain", [])[:3]
        candidates.append(
            TargetContactCandidate(
                candidate_id=_candidate_id(role_label="Named Hiring Signal", person_name=hiring_manager.name),
                role_label="Named Hiring Signal",
                title_variants=title_variants,
                fit_score=97,
                confidence=_normalize_confidence(hiring_manager.confidence),
                department=discipline_label,
                seniority="manager",
                lane="direct_hiring_chain",
                access_hint="Highest-signal lead when the posting already points to a specific person.",
                rationale=(
                    f"The job already surfaces {hiring_manager.name}"
                    + (f" ({hiring_manager.title})" if hiring_manager.title else "")
                    + ", so the discovery flow keeps that signal while verifying it against public-web results."
                ),
                guessed_name=hiring_manager.name,
                resolved_name=hiring_manager.name,
                resolved_title=hiring_manager.title,
                resolved_company=str(job.company or "").strip(),
                resolved_location=_target_contact_location_hint(job.location_raw),
                search_query=search_query,
                linkedin_search_url=(
                    f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(search_query)}"
                    if search_query
                    else ""
                ),
                google_xray_query=google_query,
                google_xray_search_url=(
                    f"https://www.google.com/search?q={quote_plus(google_query)}" if google_query else ""
                ),
                evidence=[_hit_evidence_text(hit) for hit in supporting_hits],
                source_urls=[hit.url for hit in supporting_hits if hit.url],
                source_titles=[hit.title for hit in supporting_hits if hit.title],
                resolved_in_pass=max((hit.pass_index for hit in supporting_hits), default=0),
                result_type="person",
                connection_note=_build_target_connection_note(
                    job=job,
                    department_label=discipline_label,
                    role_label="Named Hiring Signal",
                    name_placeholder="[Name]",
                ),
                follow_up_message=_build_target_follow_up_message(
                    profile=profile,
                    job=job,
                    name_placeholder="[Name]",
                    follow_up_ask=_default_follow_up_ask("direct_hiring_chain"),
                ),
            )
        )

    for blueprint in _TARGET_CONTACT_BLUEPRINTS:
        lane = str(blueprint["lane"])
        plan = lane_to_query.get(lane)
        title_variants = (
            list(plan.title_variants)
            if plan is not None and plan.title_variants
            else _title_variants_for_lane(discipline=discipline, lane=lane)
        )
        search_query = (
            plan.query if plan is not None and plan.query else _build_target_contact_search_query(job=job, title_variants=title_variants)
        )
        google_query = _build_target_contact_google_query(job=job, title_variants=title_variants)
        supporting_hits = lane_hits.get(lane, [])[:3]
        candidates.append(
            TargetContactCandidate(
                candidate_id=str(blueprint["candidate_id"]),
                role_label=str(blueprint["role_label"]),
                title_variants=title_variants,
                fit_score=int(blueprint["fit_score"]),
                confidence=str(blueprint["confidence"]),
                department=discipline_label,
                seniority=str(blueprint["seniority"]),
                lane=lane,
                access_hint=str(blueprint["access_hint"]),
                rationale=(
                    str(blueprint["rationale"])
                    + (
                        " Second-pass evidence now informs the manual verification query."
                        if supporting_hits
                        else " This lane is still unresolved and needs manual verification."
                    )
                ),
                guessed_name="",
                resolved_name="",
                resolved_title="",
                resolved_company=str(job.company or "").strip(),
                resolved_location=_target_contact_location_hint(job.location_raw),
                search_query=search_query,
                linkedin_search_url=(
                    f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(search_query)}"
                    if search_query
                    else ""
                ),
                google_xray_query=google_query,
                google_xray_search_url=(
                    f"https://www.google.com/search?q={quote_plus(google_query)}" if google_query else ""
                ),
                evidence=[_hit_evidence_text(hit) for hit in supporting_hits],
                source_urls=[hit.url for hit in supporting_hits if hit.url],
                source_titles=[hit.title for hit in supporting_hits if hit.title],
                resolved_in_pass=max((hit.pass_index for hit in supporting_hits), default=0),
                result_type="lane",
                connection_note=_build_target_connection_note(
                    job=job,
                    department_label=discipline_label,
                    role_label=str(blueprint["role_label"]),
                    name_placeholder="[Name]",
                ),
                follow_up_message=_build_target_follow_up_message(
                    profile=profile,
                    job=job,
                    name_placeholder="[Name]",
                    follow_up_ask=str(blueprint["follow_up_ask"]),
                ),
            )
        )
    deduped = _dedupe_candidates(candidates)
    deduped.sort(
        key=lambda item: (
            -int(item.fit_score),
            -_CONFIDENCE_ORDER.get(item.confidence, 0),
            item.role_label.casefold(),
        )
    )
    return deduped[:6]


def _dedupe_candidates(candidates: list[TargetContactCandidate]) -> list[TargetContactCandidate]:
    seen_keys: set[str] = set()
    deduped: list[TargetContactCandidate] = []
    for candidate in candidates:
        key = _candidate_dedupe_key(candidate)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(candidate)
    return deduped


def _dedupe_hits(hits: list[DiscoverySearchHit]) -> list[DiscoverySearchHit]:
    deduped: list[DiscoverySearchHit] = []
    seen_keys: set[str] = set()
    for hit in hits:
        key = "::".join(
            [
                str(hit.url or "").strip().lower(),
                str(hit.title or "").strip().lower(),
            ]
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(hit)
    return deduped


def _dedupe_query_plans(plans: list[DiscoveryQueryPlan]) -> list[DiscoveryQueryPlan]:
    deduped: list[DiscoveryQueryPlan] = []
    seen_queries: set[str] = set()
    for plan in plans:
        query_key = str(plan.query or "").strip().casefold()
        if not query_key or query_key in seen_queries:
            continue
        seen_queries.add(query_key)
        deduped.append(plan)
        if len(deduped) >= 6:
            break
    return deduped


def _hits_by_lane(hits: list[DiscoverySearchHit]) -> dict[str, list[DiscoverySearchHit]]:
    grouped: dict[str, list[DiscoverySearchHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.lane or "general", []).append(hit)
    return grouped


def _top_domains(hits: list[DiscoverySearchHit]) -> list[str]:
    counts: dict[str, int] = {}
    for hit in hits:
        domain = str(hit.source_domain or "").strip()
        if not domain:
            continue
        counts[domain] = counts.get(domain, 0) + 1
    return [
        domain
        for domain, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ][:4]


def _job_description_excerpt(job: JobRecord, *, limit: int = 2400) -> str:
    text = _compact_whitespace(str(job.description_text or ""))
    return _truncate_text(text, limit=limit)


def _prompt_query_lines(query_plans: list[DiscoveryQueryPlan]) -> str:
    if not query_plans:
        return "- none"
    return "\n".join(
        f"- lane={plan.lane or 'general'} | query={plan.query} | objective={plan.objective}"
        for plan in query_plans
    )


def _prompt_hit_lines(hits: list[DiscoverySearchHit], *, limit: int) -> str:
    if not hits:
        return "- none"
    return "\n".join(hit.prompt_line() for hit in hits[:limit])


def _job_context_terms(job: JobRecord) -> list[str]:
    text = " ".join(
        [
            str(job.title or ""),
            str(job.description_text or ""),
            str(job.role_category_name or ""),
        ]
    )
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&/+.-]{2,}", text)
    seen: set[str] = set()
    terms: list[str] = []
    for token in tokens:
        normalized = token.casefold()
        if normalized in _DISCOVERY_STOPWORDS:
            continue
        if len(normalized) <= 3:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(token)
        if len(terms) >= 8:
            break
    return terms


def _search_refinement_terms(job: JobRecord, hits: list[DiscoverySearchHit]) -> list[str]:
    terms = list(_job_context_terms(job))
    snippet_tokens = re.findall(
        r"[A-Za-z][A-Za-z0-9&/+.-]{2,}",
        " ".join(f"{hit.title} {hit.snippet}" for hit in hits[:10]),
    )
    seen = {term.casefold() for term in terms}
    for token in snippet_tokens:
        normalized = token.casefold()
        if normalized in _DISCOVERY_STOPWORDS or len(normalized) <= 3:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(token)
        if len(terms) >= 10:
            break
    return terms


def _title_variants_for_lane(*, discipline: dict[str, Any], lane: str) -> list[str]:
    title_key = _LANE_TO_TITLE_KEY.get(str(lane or "").strip(), "manager_titles")
    variants = [
        _compact_whitespace(str(item))
        for item in (discipline.get(title_key) or [])
        if _compact_whitespace(str(item))
    ]
    return variants


def _default_fit_score_for_lane(lane: str) -> int:
    blueprint = _BLUEPRINT_BY_LANE.get(str(lane or "").strip())
    return int(blueprint.get("fit_score", 70)) if blueprint else 70


def _default_follow_up_ask(lane: str) -> str:
    blueprint = _BLUEPRINT_BY_LANE.get(str(lane or "").strip())
    return str(blueprint.get("follow_up_ask") or "If you are open to it, I would value any guidance on the team or process.")


def _default_access_hint(lane: str) -> str:
    blueprint = _BLUEPRINT_BY_LANE.get(str(lane or "").strip())
    return str(blueprint.get("access_hint") or "Useful lane for validating ownership or team context.")


def _default_seniority_for_lane(lane: str) -> str:
    blueprint = _BLUEPRINT_BY_LANE.get(str(lane or "").strip())
    return str(blueprint.get("seniority") or "manager")


def _role_label_for_lane(lane: str) -> str:
    blueprint = _BLUEPRINT_BY_LANE.get(str(lane or "").strip())
    return str(blueprint.get("role_label") or "Target Contact")


def _normalize_confidence(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "medium"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [_compact_whitespace(str(item)) for item in value if _compact_whitespace(str(item))]
        return _dedupe_strings(items)
    if isinstance(value, str) and value.strip():
        return [_compact_whitespace(value)]
    return []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = str(value or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(str(value).strip())
    return deduped


def _candidate_id(*, role_label: str, person_name: str) -> str:
    base = f"{role_label} {person_name}".strip()
    return _NON_ALNUM.sub("_", base.casefold()).strip("_") or "target_contact"


def _resolve_candidate_pass(source_urls: list[str], hit_by_url: dict[str, DiscoverySearchHit]) -> int:
    if not source_urls:
        return 0
    return max(
        (hit_by_url.get(url).pass_index for url in source_urls if hit_by_url.get(url) is not None),
        default=0,
    )


def _hit_evidence_text(hit: DiscoverySearchHit) -> str:
    return _compact_whitespace(
        " | ".join(part for part in [hit.title, hit.snippet] if _compact_whitespace(part))
    )


def _source_domain(url: str) -> str:
    hostname = urlparse(str(url or "").strip()).hostname or ""
    return hostname.casefold()


def _build_resolution_summary(candidates: list[TargetContactCandidate]) -> str:
    if not candidates:
        return "No candidate lanes could be built from the current discovery passes."
    named_count = sum(1 for candidate in candidates if candidate.resolved_name)
    pass_two_count = sum(1 for candidate in candidates if int(candidate.resolved_in_pass or 0) >= 2)
    return (
        f"Returned {len(candidates)} candidate lane"
        f"{'' if len(candidates) == 1 else 's'}, including {named_count} named result"
        f"{'' if named_count == 1 else 's'}. "
        f"{pass_two_count} candidate"
        f"{'' if pass_two_count == 1 else 's'} carry pass-2 evidence."
    )


def _truncate_text(value: str, *, limit: int) -> str:
    text = _compact_whitespace(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _strip_json_fences(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clamp_score(value: Any, *, default: int) -> int:
    try:
        numeric = int(value)
    except Exception:
        numeric = default
    return max(1, min(99, numeric))


def _candidate_dedupe_key(candidate: TargetContactCandidate) -> str:
    if candidate.resolved_name:
        return f"person::{candidate.resolved_name.casefold()}"
    return "::".join(
        [
            candidate.role_label.casefold(),
            candidate.lane.casefold(),
            candidate.search_query.casefold(),
        ]
    )
