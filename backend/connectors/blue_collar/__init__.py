from .collector import (
    PORTAL_STRATEGIES,
    PortalStrategy,
    collect_jobs_from_portals,
    get_portal_strategy,
    list_portal_strategy_ids,
)
from .strategies import (
    compact_whitespace,
    scrape_arbeitsagentur_jobs,
    scrape_indeed_jobs,
    scrape_linkedin_jobs,
    scrape_stepstone_jobs,
)

__all__ = [
    "PORTAL_STRATEGIES",
    "PortalStrategy",
    "collect_jobs_from_portals",
    "compact_whitespace",
    "get_portal_strategy",
    "list_portal_strategy_ids",
    "scrape_arbeitsagentur_jobs",
    "scrape_indeed_jobs",
    "scrape_linkedin_jobs",
    "scrape_stepstone_jobs",
]
