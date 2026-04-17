import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests as std_requests
from bs4 import BeautifulSoup
from scrapeops_python_requests.scrapeops_requests import ScrapeOpsRequests

from job_models import FILTER_STATUS_PENDING, SOURCE_TYPE_LINKEDIN_SEARCH
from job_seeker_config import load_project_dotenv

from .common import compact_whitespace


LINKEDIN_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_posted_age_hours(posted_text: str):
    text = compact_whitespace((posted_text or "").lower())
    if not text:
        return None

    if "just now" in text or "today" in text:
        return 0.0
    if "yesterday" in text:
        return 24.0

    match = re.search(r"(\d+)\s*(minute|hour|day|week|month)s?", text)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    unit_hours = {
        "minute": 1 / 60,
        "hour": 1,
        "day": 24,
        "week": 24 * 7,
        "month": 24 * 30,
    }
    return round(amount * unit_hours.get(unit, 0), 2)


def extract_posted_time_text(soup: BeautifulSoup, page_text: str) -> str:
    selectors = [
        "span.posted-time-ago__text",
        "span.topcard__flavor--metadata",
        "span.topcard__flavor--bullet",
        "time",
    ]

    for selector in selectors:
        for node in soup.select(selector):
            text = compact_whitespace(node.get_text(separator=" ", strip=True))
            lowered = text.lower()
            if any(
                token in lowered
                for token in ["ago", "just now", "today", "yesterday", "reposted", "hour", "day", "week", "month"]
            ):
                return text

    fallback_match = re.search(
        r"(?i)(reposted\s+)?(\d+\s+(minute|hour|day|week|month)s?\s+ago|just now|today|yesterday)",
        page_text or "",
    )
    return compact_whitespace(fallback_match.group(0)) if fallback_match else ""


def extract_applicant_count(soup: BeautifulSoup, page_text: str):
    applicant_patterns = [
        re.compile(r"(?i)be among the first\s+(\d+)\s+applicants?"),
        re.compile(r"(?i)(?:over|more than)\s+(\d+)\+?\s+applicants?"),
        re.compile(r"(?i)(\d{1,3}(?:[,\.\s]\d{3})*|\d+)\+?\s+applicants?"),
    ]

    def parse_from_text(text: str):
        for pattern in applicant_patterns:
            match = pattern.search(text or "")
            if not match:
                continue
            digits = re.sub(r"[^\d]", "", match.group(1))
            if digits:
                return int(digits)
        return None

    selectors = [
        "figcaption.num-applicants__caption",
        "span.num-applicants__caption",
        "span.topcard__flavor--metadata",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            count = parse_from_text(compact_whitespace(node.get_text(separator=" ", strip=True)))
            if count is not None:
                return count

    return parse_from_text(page_text or "")


def coerce_applicant_count(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        digits = re.sub(r"[^\d]", "", str(value))
        return int(digits) if digits else None


def is_easy_apply(value) -> bool:
    return value is True


def priority_tier(job, low_applicant_threshold: int) -> int:
    easy = is_easy_apply(job.get("easy_apply_status"))
    applicants = coerce_applicant_count(job.get("applicant_count"))
    low_applicants = applicants is not None and applicants <= low_applicant_threshold

    if low_applicants and not easy:
        return 1
    if low_applicants and easy:
        return 2
    if not low_applicants and not easy:
        return 3
    return 4


def priority_sort_key(job, low_applicant_threshold: int):
    posted_age_hours = job.get("posted_age_hours")
    applicant_count = coerce_applicant_count(job.get("applicant_count"))

    posted_missing = posted_age_hours is None
    applicants_missing = applicant_count is None

    posted_value = float(posted_age_hours) if not posted_missing else float("inf")
    applicants_value = int(applicant_count) if not applicants_missing else 10**9

    return (
        priority_tier(job, low_applicant_threshold),
        1 if posted_missing else 0,
        posted_value,
        1 if applicants_missing else 0,
        applicants_value,
        str(job.get("job_id", "")),
    )


def build_scrape_requests_client():
    load_project_dotenv()
    scrapeops_api_key = os.getenv("SCRAPEOPS_API_KEY")
    if not scrapeops_api_key:
        raise RuntimeError(
            "Missing SCRAPEOPS_API_KEY in environment/user_config/.env. "
            "LinkedIn scraping requires ScrapeOps."
        )

    scrapeops_logger = ScrapeOpsRequests(
        scrapeops_api_key=scrapeops_api_key,
        spider_name="LinkedIn Smart Scraper",
        job_name="Germany-AI-Filtered",
    )
    so_requests = scrapeops_logger.RequestsWrapper()
    return scrapeops_api_key, so_requests


def build_clients():
    scrapeops_api_key, so_requests = build_scrape_requests_client()
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

    if not deepseek_api_key:
        print(
            "ERROR: Missing API keys in environment/user_config/.env "
            "(SCRAPEOPS_API_KEY and DEEPSEEK_API_KEY are required)."
        )
        raise SystemExit(1)

    return scrapeops_api_key, deepseek_api_key, so_requests


def fetch_initial_list(
    keyword: str,
    so_requests,
    max_pages: int,
    geo_id: str,
    time_posted_seconds: int,
    experience_levels,
    forbidden_title_words,
    page_fetch_sleep_seconds: float,
):
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    found_jobs = []

    for page in range(max_pages):
        start_index = page * 25
        query_parts = [
            f"keywords={quote(keyword)}",
            f"geoId={quote(str(geo_id))}",
            f"start={start_index}",
        ]
        if int(time_posted_seconds) > 0:
            query_parts.append(f"f_TPR=r{int(time_posted_seconds)}")
        if experience_levels:
            exp_values = [str(int(level)) for level in experience_levels if str(level).strip()]
            if exp_values:
                query_parts.append(f"f_E={','.join(exp_values)}")
        query_params = "&".join(query_parts)
        target_url = f"{base_url}?{query_params}"

        print(f"[Stage1] {keyword} page {page + 1}: fetching")

        try:
            response = so_requests.get(target_url)
            if response.status_code != 200:
                break

            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.find_all("li")
            if not items:
                break

            for item in items:
                card_text = item.get_text(separator=" ", strip=True).lower()
                if "reposted" in card_text:
                    continue

                base_card = item.find("div", {"class": "base-card"})
                if not base_card:
                    continue

                title_tag = item.find("h3", {"class": "base-search-card__title"})
                company_tag = item.find("h4", {"class": "base-search-card__subtitle"})
                location_tag = item.find("span", {"class": "job-search-card__location"})
                if not title_tag or not company_tag:
                    continue

                title = title_tag.get_text(strip=True)
                if any(word in title.lower() for word in forbidden_title_words):
                    continue

                company = company_tag.get_text(strip=True)
                location_raw = location_tag.get_text(strip=True) if location_tag else ""
                urn = base_card.get("data-entity-urn", "")
                if ":" not in urn:
                    continue

                job_id = urn.split(":")[-1]
                found_jobs.append(
                    {
                        "job_id": job_id,
                        "title": title,
                        "company": company,
                        "location_raw": location_raw,
                        "keyword": keyword,
                        "link": f"https://www.linkedin.com/jobs/view/{job_id}",
                        "linkedin_link": f"https://www.linkedin.com/jobs/view/{job_id}",
                        "source_url": f"https://www.linkedin.com/jobs/view/{job_id}",
                        "source_type": SOURCE_TYPE_LINKEDIN_SEARCH,
                        "filter_status": FILTER_STATUS_PENDING,
                    }
                )

            if page_fetch_sleep_seconds > 0:
                time.sleep(page_fetch_sleep_seconds)
        except Exception as exc:
            print(f"[Stage1] error for keyword={keyword} page={page + 1}: {exc}")
            break

    return found_jobs


def fetch_linkedin_job_posting_response(
    job_id: str,
    so_requests,
    scrapeops_api_key: str,
    use_proxy_fallback: bool,
):
    target_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    attempts = []

    resp = so_requests.get(target_url, headers=LINKEDIN_REQUEST_HEADERS, timeout=45)
    attempts.append(("so_requests", resp.status_code))

    if resp.status_code != 200:
        resp = std_requests.get(target_url, headers=LINKEDIN_REQUEST_HEADERS, timeout=45)
        attempts.append(("direct", resp.status_code))

    if resp.status_code != 200 and use_proxy_fallback:
        proxy_url = "https://proxy.scrapeops.io/v1/"
        params = {
            "api_key": scrapeops_api_key,
            "url": target_url,
            "residential": "true",
            "render_js": "true",
        }
        resp = std_requests.get(proxy_url, params=params, headers=LINKEDIN_REQUEST_HEADERS, timeout=45)
        attempts.append(("scrapeops_proxy", resp.status_code))

    return target_url, resp, attempts


def extract_linkedin_job_header_fields(soup: BeautifulSoup):
    title_selectors = [
        "h2.top-card-layout__title",
        "h1.top-card-layout__title",
        "h1",
    ]
    company_selectors = [
        "a.topcard__org-name-link",
        "span.topcard__flavor",
        "a.top-card-layout__company-url",
        "span.top-card-layout__second-subline a",
    ]
    location_selectors = [
        "span.topcard__flavor--bullet",
        "span.top-card-layout__first-subline",
        "span.top-card-layout__second-subline",
    ]

    def extract_text(selectors):
        for selector in selectors:
            for node in soup.select(selector):
                text = compact_whitespace(node.get_text(separator=" ", strip=True))
                if text:
                    return text
        return ""

    title = extract_text(title_selectors)
    company = extract_text(company_selectors)
    location_raw = extract_text(location_selectors)

    if location_raw and " ago" in location_raw.lower():
        location_raw = ""

    return {
        "title": title,
        "company": company,
        "location_raw": location_raw,
    }


def parse_linkedin_job_posting_html(job_id: str, html: str):
    html_lower = html.lower()
    soup = BeautifulSoup(html, "html.parser")
    page_text = compact_whitespace(soup.get_text(separator=" ", strip=True))
    header_fields = extract_linkedin_job_header_fields(soup)

    primary_apply = soup.select_one(
        ".top-card-layout__cta--primary[data-tracking-control-name*='public_jobs_apply-link']"
    )
    apply_trackings = [
        (el.get("data-tracking-control-name") or "").lower()
        for el in soup.select("[data-tracking-control-name*='public_jobs_apply-link']")
    ]
    primary_text = primary_apply.get_text(separator=" ", strip=True).lower() if primary_apply else ""

    if "easy apply" in primary_text or "einfach bewerben" in primary_text:
        easy_apply_status = True
    elif any("easy_apply" in item for item in apply_trackings):
        easy_apply_status = True
    elif any("onsite" in item for item in apply_trackings):
        easy_apply_status = True
    elif any("offsite" in item for item in apply_trackings):
        easy_apply_status = False
    elif "easy apply" in html_lower or "einfach bewerben" in html_lower:
        easy_apply_status = True
    elif "apply on company website" in html_lower:
        easy_apply_status = False
    else:
        easy_apply_status = "unknown"

    desc_tag = (
        soup.find("div", {"class": "show-more-less-html__markup"})
        or soup.find("div", {"class": "description__text"})
        or soup.select_one("section.show-more-less-html")
    )
    description = desc_tag.get_text(separator="\n", strip=True) if desc_tag else None

    def normalize_href(raw_href: str):
        href = (raw_href or "").strip()
        if not href or href == "#" or href.lower().startswith("javascript:"):
            return None
        if href.startswith("//"):
            href = f"https:{href}"
        elif href.startswith("/"):
            href = f"https://www.linkedin.com{href}"
        return href

    def decode_session_redirect(url: str):
        try:
            parsed = urlparse(url)
            redirect_value = parse_qs(parsed.query).get("session_redirect", [None])[0]
            if redirect_value:
                return unquote(redirect_value)
        except Exception:
            pass
        return url

    linkedin_default = f"https://www.linkedin.com/jobs/view/{job_id}"
    external_apply_link = None
    linkedin_apply_link = None

    apply_elements = soup.select("[data-tracking-control-name*='public_jobs_apply-link'], [data-apply-url], a[href]")
    for element in apply_elements:
        tracking = (element.get("data-tracking-control-name") or "").lower()
        href = normalize_href(
            element.get("href") or element.get("data-apply-url") or element.get("data-test-apply-url")
        )
        if not href:
            continue

        if "linkedin.com/login" in href.lower() or "/uas/login" in href.lower():
            href = decode_session_redirect(href)

        href_lower = href.lower()
        is_apply_candidate = "apply" in tracking or "apply" in href_lower or "jobs/view" in href_lower
        if not is_apply_candidate:
            continue

        if "linkedin.com" not in href_lower:
            external_apply_link = href
            break

        if "linkedin.com/jobs/view" in href_lower and not linkedin_apply_link:
            linkedin_apply_link = href

    if external_apply_link:
        apply_link = external_apply_link
        apply_link_source = "external"
    elif linkedin_apply_link:
        apply_link = linkedin_apply_link
        apply_link_source = "linkedin"
    else:
        apply_link = linkedin_default
        apply_link_source = "linkedin_fallback"

    posted_time_text = extract_posted_time_text(soup, page_text)
    posted_age_hours = parse_posted_age_hours(posted_time_text)
    applicant_count = extract_applicant_count(soup, page_text)
    posted_datetime_estimated_utc = None
    if posted_age_hours is not None:
        posted_datetime_estimated_utc = (
            datetime.now(timezone.utc) - timedelta(hours=float(posted_age_hours))
        ).isoformat(timespec="seconds")

    return {
        **header_fields,
        "easy_apply_status": easy_apply_status,
        "description": description,
        "apply_link": apply_link,
        "apply_link_source": apply_link_source,
        "posted_time_text": posted_time_text,
        "posted_age_hours": posted_age_hours,
        "posted_datetime_estimated_utc": posted_datetime_estimated_utc,
        "applicant_count": applicant_count,
        "enrich_error": None if description else "Description container not found",
    }


def enrich_job(
    job_id: str,
    so_requests,
    scrapeops_api_key: str,
    debug_enrich_blocks: bool,
    use_proxy_fallback: bool,
):
    try:
        target_url, resp, attempts = fetch_linkedin_job_posting_response(
            job_id=job_id,
            so_requests=so_requests,
            scrapeops_api_key=scrapeops_api_key,
            use_proxy_fallback=use_proxy_fallback,
        )

        if resp.status_code != 200:
            if debug_enrich_blocks:
                print("\n===== ENRICH DEBUG (BLOCKED) =====")
                print("Status:", resp.status_code)
                print("Attempts:", attempts)
                print("Body preview:", resp.text[:300])
                print("==================================\n")

            return {
                "easy_apply_status": "unknown",
                "description": None,
                "title": "",
                "company": "",
                "location_raw": "",
                "apply_link": f"https://www.linkedin.com/jobs/view/{job_id}",
                "apply_link_source": "linkedin_fallback",
                "enrich_error": f"Failed (Status {resp.status_code}) | Attempts={attempts}",
                "status_code": resp.status_code,
            }

        parsed = parse_linkedin_job_posting_html(job_id=job_id, html=resp.text)
        return {
            **parsed,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {
            "easy_apply_status": "unknown",
            "description": None,
            "title": "",
            "company": "",
            "location_raw": "",
            "apply_link": f"https://www.linkedin.com/jobs/view/{job_id}",
            "apply_link_source": "linkedin_fallback",
            "posted_time_text": "",
            "posted_age_hours": None,
            "posted_datetime_estimated_utc": None,
            "applicant_count": None,
            "enrich_error": f"Error: {exc}",
            "status_code": -1,
        }
