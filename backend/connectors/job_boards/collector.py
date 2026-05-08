from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from . import strategies


PortalFetcher = Callable[..., Tuple[List[Dict], List[str]]]


@dataclass(frozen=True, slots=True)
class PortalStrategy:
    portal_id: str
    name: str
    fetcher: PortalFetcher


PORTAL_STRATEGIES: dict[str, PortalStrategy] = {
    "indeed": PortalStrategy("indeed", "Indeed Germany", strategies.scrape_indeed_jobs),
    "arbeitsagentur": PortalStrategy(
        "arbeitsagentur",
        "Bundesagentur fuer Arbeit",
        strategies.scrape_arbeitsagentur_jobs,
    ),
    "stepstone": PortalStrategy("stepstone", "StepStone Germany", strategies.scrape_stepstone_jobs),
    "linkedin": PortalStrategy("linkedin", "LinkedIn Guest Jobs", strategies.scrape_linkedin_jobs),
}

ADDITIONAL_PORTAL_STRATEGIES: dict[str, PortalStrategy] = {
    "glassdoor": PortalStrategy("glassdoor", "Glassdoor", strategies.scrape_glassdoor_jobs),
    "ziprecruiter": PortalStrategy("ziprecruiter", "ZipRecruiter", strategies.scrape_ziprecruiter_jobs),
    "monster": PortalStrategy("monster", "Monster", strategies.scrape_monster_jobs),
    "careerbuilder": PortalStrategy("careerbuilder", "CareerBuilder", strategies.scrape_careerbuilder_jobs),
    "careerjet": PortalStrategy("careerjet", "Careerjet", strategies.scrape_careerjet_jobs),
    "reed": PortalStrategy("reed", "Reed.co.uk", strategies.scrape_reed_jobs),
    "totaljobs": PortalStrategy("totaljobs", "Totaljobs", strategies.scrape_totaljobs_jobs),
    "jobsdb": PortalStrategy("jobsdb", "JobsDB", strategies.scrape_jobsdb_jobs),
}


def get_portal_strategy(portal_id: str) -> PortalStrategy:
    normalized = str(portal_id or "").strip().lower()
    if normalized in PORTAL_STRATEGIES:
        return PORTAL_STRATEGIES[normalized]
    if normalized in ADDITIONAL_PORTAL_STRATEGIES:
        return ADDITIONAL_PORTAL_STRATEGIES[normalized]
    raise KeyError(f"Unsupported portal strategy: {portal_id}")


def list_portal_strategy_ids() -> list[str]:
    return sorted(PORTAL_STRATEGIES.keys())


def collect_jobs_from_portals(
    portals: List[str],
    keywords: List[str],
    cities: List[str],
    max_pages: int,
    posted_within_days: int,
    radius_km: int,
    timeout_seconds: int,
    max_jobs_total: int = 0,
    arbeitsagentur_detail_fetch_limit: int = 20,
) -> Tuple[List[Dict], Dict]:
    all_jobs: List[Dict] = []
    source_log = {
        "started_at_utc": strategies.now_utc_iso(),
        "by_portal": {},
        "errors": [],
        "stopped_early": False,
    }

    for portal_name in portals:
        if max_jobs_total > 0 and len(all_jobs) >= max_jobs_total:
            source_log["stopped_early"] = True
            break

        portal = str(portal_name or "").strip().lower()
        portal_count = 0
        portal_errors: List[str] = []
        portal_hard_blocked = False

        for keyword in keywords:
            if max_jobs_total > 0 and len(all_jobs) >= max_jobs_total:
                source_log["stopped_early"] = True
                break
            if portal_hard_blocked:
                break

            keyword_clean = strategies.compact_whitespace(keyword)
            if not keyword_clean:
                continue

            for city in cities:
                if max_jobs_total > 0 and len(all_jobs) >= max_jobs_total:
                    source_log["stopped_early"] = True
                    break
                if portal_hard_blocked:
                    break

                city_clean = strategies.compact_whitespace(city)
                if not city_clean:
                    continue

                jobs: List[Dict] = []
                errors: List[str] = []

                print(f"[Stage1] portal={portal} keyword='{keyword_clean}' city='{city_clean}' ...")
                try:
                    strategy = get_portal_strategy(portal)
                    if portal == "indeed":
                        jobs, errors = strategy.fetcher(
                            keyword=keyword_clean,
                            city=city_clean,
                            max_pages=max_pages,
                            posted_within_days=posted_within_days,
                            timeout_seconds=timeout_seconds,
                        )
                    elif portal == "arbeitsagentur":
                        jobs, errors = strategy.fetcher(
                            keyword=keyword_clean,
                            city=city_clean,
                            max_pages=max_pages,
                            posted_within_days=posted_within_days,
                            timeout_seconds=timeout_seconds,
                            radius_km=radius_km,
                            detail_fetch_limit=max(0, int(arbeitsagentur_detail_fetch_limit)),
                        )
                    elif portal == "stepstone":
                        jobs, errors = strategy.fetcher(
                            keyword=keyword_clean,
                            city=city_clean,
                            max_pages=max_pages,
                            radius_km=radius_km,
                            timeout_seconds=timeout_seconds,
                        )
                    elif portal == "linkedin":
                        jobs, errors = strategy.fetcher(
                            keyword=keyword_clean,
                            city=city_clean,
                            max_pages=max_pages,
                            posted_within_days=posted_within_days,
                            timeout_seconds=timeout_seconds,
                        )
                    elif portal in {
                        "glassdoor",
                        "ziprecruiter",
                        "monster",
                        "careerbuilder",
                        "careerjet",
                        "reed",
                        "totaljobs",
                        "jobsdb",
                    }:
                        jobs, errors = strategy.fetcher(
                            keyword=keyword_clean,
                            city=city_clean,
                            max_pages=max_pages,
                            posted_within_days=posted_within_days,
                            timeout_seconds=timeout_seconds,
                        )
                except KeyError:
                    errors = [f"Unsupported portal: {portal}"]

                portal_count += len(jobs)
                portal_errors.extend(errors)
                all_jobs.extend(jobs)
                print(
                    f"[Stage1] portal={portal} keyword='{keyword_clean}' city='{city_clean}' "
                    f"jobs={len(jobs)} errors={len(errors)} total_so_far={len(all_jobs)}"
                )

                if portal == "indeed":
                    if any("status=403" in item or "status=429" in item for item in errors):
                        portal_hard_blocked = True
                        portal_errors.append(
                            "Indeed appears blocked (403/429). Remaining Indeed combinations skipped for this run."
                        )
                if max_jobs_total > 0 and len(all_jobs) >= max_jobs_total:
                    source_log["stopped_early"] = True
                    break

        source_log["by_portal"][portal] = {
            "jobs_collected": portal_count,
            "errors_count": len(portal_errors),
            "errors": portal_errors,
        }
        source_log["errors"].extend(portal_errors)

    source_log["finished_at_utc"] = strategies.now_utc_iso()
    source_log["total_jobs_collected"] = len(all_jobs)
    return all_jobs, source_log
