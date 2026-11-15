"""Local, one-shot workbook acquisition. Never publishes or loads provider credentials.

Uses the application's parsers and ATS adapters; cache and receipts belong to this
run only. Workbook values are data, never executable instructions.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from contextlib import nullcontext
import csv
from functools import lru_cache
from datetime import datetime, timezone
import hashlib
from html import unescape
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode, quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openpyxl
import requests
from bs4 import BeautifulSoup
from backend.connectors.ats_router import detect_ats, fetch_ats_snapshot
from backend.connectors.generic_jsonld import _json_ld_values, _job_from_json_ld, _job_from_html
from backend.connectors.employer_site_fallbacks import (
    extract_embedded_jobs,
    extract_payload_jobs,
    fetch_browser_snapshot,
)
from backend.acquisition.job_page_evidence import generic_employer_non_job_reason

HEADERS = [
    "rank",
    "company_name",
    "company_website",
    "career_url",
    "example_vacancy",
    "example_location",
    "evidence_url",
    "extraction_notes",
    "api_endpoint",
    "api_request_body",
    "workbook_checked_on",
    "verification_evidence",
    "scope_notes",
    "batch",
]
FIELDS = [
    "company_name",
    "rank",
    "batch",
    "legal_employer",
    "company_website",
    "career_url",
    "title",
    "job_id",
    "job_detail_url",
    "description",
    "responsibilities",
    "requirements",
    "qualifications",
    "skills",
    "seniority",
    "employment_type",
    "working_hours",
    "department",
    "function",
    "industry",
    "salary",
    "salary_currency",
    "salary_period",
    "location",
    "country",
    "region",
    "city",
    "postal_code",
    "workplace",
    "language_requirements",
    "date_posted",
    "date_posted_raw",
    "source_start_date",
    "source_end_date",
    "application_deadline",
    "date_collected",
    "source_platform",
    "source_tenant",
    "extraction_method",
    "deduplication_basis",
    "source_page",
    "raw_record_file",
    "scope_notes",
    "employer_match",
    "country_scope",
    "job_id_aliases",
    "additional_raw_record_files",
]
DETAIL = re.compile(
    r"/job/[^/]+|/jobs/[^/?]+|/stellenangebot[^/]*/[^/?]+|/position/[^/?]+|/vacanc[^/]*/[^/?]+|/requisition/|jobdetail|jobId=|job_id=|/offer/|/stellenanzeige",
    re.I,
)
CAREER = re.compile(r"career|karriere|stellen|vacanc|jobs|recruit|jobsearch", re.I)
NEXT = re.compile(r"^(next(?: page)?|weiter|nächste(?: seite)?|mehr (?:jobs|stellen)|load more|show more|›|»)$", re.I)
BLOCK = re.compile(
    r"cf-chl-|verify you are human|just a moment|access denied|captcha-container|g-recaptcha|hcaptcha|enable javascript and cookies",
    re.I,
)
EXCLUDED_HOSTS = (
    "linkedin.com",
    "indeed.com",
    "google.com",
    "bing.com",
    "glassdoor.com",
    "stepstone.de",
    "facebook.com",
)
BROWSER_SLOTS = threading.BoundedSemaphore(2)
PARSERS = None


def now():
    return datetime.now(timezone.utc).isoformat()


def text(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def plain(v):
    value = text(v)
    if "<" not in value or ">" not in value:
        return unescape(value).strip()
    return BeautifulSoup(value, "lxml").get_text("\n", strip=True)


def canonical(v, base=""):
    p = urlsplit(urljoin(base, text(v).strip()))
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return ""
    if any(p.hostname == h or p.hostname.endswith("." + h) for h in EXCLUDED_HOSTS):
        return ""
    if re.search(r"\.(pdf|png|jpg|svg|zip|docx|xlsx|css|js)$", p.path, re.I):
        return ""
    return urlunsplit(
        (
            p.scheme,
            p.netloc.lower(),
            p.path,
            urlencode(
                [
                    (k, v)
                    for k, v in parse_qsl(p.query, keep_blank_values=True)
                    if not k.startswith(("utm_", "gclid", "fbclid"))
                ]
            ),
            "",
        )
    )


def same_listing_scope(candidate, current):
    """Pagination may change cursors, but must not branch into filter combinations."""
    a, b = urlsplit(candidate), urlsplit(current)
    cursor = {"startrow", "offset", "page", "p", "start", "pageindex", "pagenumber"}

    def query(p):
        return sorted(
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in cursor and not k.startswith("utm_")
        )

    return a.netloc == b.netloc and a.path.rstrip("/") == b.path.rstrip("/") and query(a) == query(b)


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def identity(j):
    return (j["source_platform"], j["source_tenant"], j["job_id"]) if j["job_id"] else ("url", j["job_detail_url"])


def deduplicate(records):
    """Merge extraction variants by stable identity OR their shared detail URL."""
    records = sorted(
        records, key=lambda j: sum(bool(j.get(k)) for k in FIELDS) + (10 if j.get("description") else 0), reverse=True
    )
    by_id = {}
    by_url = {}
    result = []
    removed = 0
    for j in records:
        key = identity(j)
        url = canonical(j["job_detail_url"])
        prior = by_id.get(key) or by_url.get(url)
        if prior is None:
            prior = dict(j)
            result.append(prior)
        else:
            removed += 1
            if j.get("job_id") and j["job_id"] != prior.get("job_id"):
                aliases = json.loads(prior.get("job_id_aliases") or "[]")
                aliases.append(j["job_id"])
                prior["job_id_aliases"] = json.dumps(sorted(set(aliases)))
            if j.get("raw_record_file") != prior.get("raw_record_file"):
                refs = json.loads(prior.get("additional_raw_record_files") or "[]")
                refs.append(j["raw_record_file"])
                prior["additional_raw_record_files"] = json.dumps(sorted(set(refs)))
            for k in FIELDS:
                if not prior.get(k) and j.get(k):
                    prior[k] = j[k]
        by_id[key] = prior
        by_url[url] = prior
    return result, removed


def validate(out):
    with (out / "jobs.csv").open(encoding="utf-8-sig", newline="") as f:
        jobs = list(csv.DictReader(f))
    chosen = []
    counts = {}
    for j in jobs:
        method = j["extraction_method"]
        if counts.get(method, 0) >= 2:
            continue
        counts[method] = counts.get(method, 0) + 1
        chosen.append(j)
    fresh = (
        out / "live_validation" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    )
    fresh.mkdir(parents=True, exist_ok=True)
    t = Transport(fresh)
    results = []
    for j in chosen:
        r = {k: j[k] for k in ("company_name", "title", "job_id", "job_detail_url", "location", "extraction_method")}
        try:
            page = t.request(j["job_detail_url"])
            r.update(http_status=page.status_code, resolved_url=page.url)
            _, found = extract(page.text, page.url)
            if j["extraction_method"] == "workday_cxs":
                payload = t.request(j["source_page"]).json()
                info = payload.get("jobPostingInfo", {})
                live = [
                    {
                        "title": info.get("title"),
                        "job_id": info.get("jobReqId"),
                        "url": info.get("externalUrl"),
                        "location": info.get("location"),
                    }
                ]
                r["verification_method"] = "fresh_direct_page_and_CXS_detail"
            elif j["extraction_method"] == "bosch_public_api_smartrecruiters_detail":
                info = t.request(j["source_page"]).json()
                loc = info.get("location") or {}
                live = [
                    {
                        "title": info.get("name"),
                        "job_id": text(info.get("id")),
                        "url": j["job_detail_url"],
                        "location": ", ".join(text(loc.get(k)) for k in ("city", "region") if loc.get(k)),
                    }
                ]
                r["verification_method"] = "fresh_direct_page_and_SmartRecruiters_detail"
            else:
                live = [x[0] for x in found]
                r["verification_method"] = "fresh_direct_page"
                if j["extraction_method"] == "db_server_paginated_html":
                    live = [
                        _job_from_json_ld(raw, page_url=page.url, raw_html="")
                        for raw in db_jobpostings(BeautifulSoup(page.text, "lxml"))
                    ]
                    r["verification_method"] = "fresh_DB_detail_JSONLD"
            matched = next((v for v in live if text(v.get("job_id")) == j["job_id"] and j["job_id"]), None)
            matched = matched or next(
                (
                    v
                    for v in live
                    if canonical(v.get("job_detail_url") or v.get("url")) == canonical(j["job_detail_url"])
                ),
                None,
            )
            if not matched:
                r.update(
                    result="unverified", limitation="No matching structured/detail record in fresh static response"
                )
            else:
                r.update(
                    live_title=plain(matched.get("title")),
                    live_job_id=text(matched.get("job_id")),
                    live_location=text(matched.get("location")),
                )
                r["title_match"] = r["live_title"] == j["title"]
                r["id_match"] = r["live_job_id"] == j["job_id"] if j["job_id"] else "not_available"
                if j["extraction_method"] == "db_server_paginated_html" and r["id_match"] is False:
                    r["id_match"] = "not_comparable_listing_vs_detail_identifier"
                    r["limitation"] = (
                        "Stored ID is data-job-id from the listing; detail JSONLD uses a separate identifier. Title, URL and location checked; listing ID not reverified."
                    )
                if j["extraction_method"] == "eightfold_public_api":
                    api = t.request(j["source_page"]).json()
                    position = next(
                        (
                            v
                            for v in api.get("positions", [])
                            if text(v.get("ats_job_id") or v.get("id")) == j["job_id"]
                        ),
                        None,
                    )
                    r["id_match"] = position is not None
                    r["verification_method"] = "fresh_direct_page_and_Eightfold_API"
                r["location_match"] = r["live_location"] == j["location"] if j["location"] else "not_available"
                if r["location_match"] is False and j["location"] and j["location"] in r["live_location"]:
                    r["location_match"] = True
                    r["location_comparison"] = "stored location is an explicit subset of the fresh full address"
                r["url_match"] = canonical(matched.get("job_detail_url") or matched.get("url")) == canonical(
                    j["job_detail_url"]
                )
                r["result"] = (
                    "matched"
                    if r["title_match"]
                    and r["id_match"] is not False
                    and r["location_match"] is not False
                    and r["url_match"]
                    else "mismatch"
                )
        except Exception as exc:
            r.update(result="failed_or_blocked", limitation=str(exc)[:180])
        r["checked_at"] = now()
        results.append(r)
    write_csv(out / "live_validation.csv", results)
    print(
        json.dumps(
            {
                "sample_size": len(results),
                "results": {
                    k: sum(r["result"] == k for r in results)
                    for k in ("matched", "mismatch", "unverified", "failed_or_blocked")
                },
            }
        )
    )


def atomic_json(path, value):
    """Keep the last complete file until its replacement is fully written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False
        ) as f:
            temp = Path(f.name)
            json.dump(value, f, ensure_ascii=False, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def saved_json(path, kind="object"):
    """Preserve damaged restart state and treat it as missing, not completed."""
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        valid = isinstance(value, dict)
        if kind == "receipt":
            valid = (
                valid
                and isinstance(value.get("status"), dict)
                and bool(value["status"].get("rank"))
                and isinstance(value.get("jobs"), list)
            )
        elif kind == "cache":
            valid = valid and all(k in value for k in ("url", "status", "body"))
        if not valid:
            raise ValueError("invalid_saved_schema")
        return value
    except FileNotFoundError:
        return None
    except (ValueError, UnicodeError):
        backup = path.with_name(path.name + ".corrupt-" + uuid.uuid4().hex)
        path.rename(backup)
        print(
            json.dumps({"recovery": "damaged_saved_file_preserved", "file": str(path), "backup": str(backup)}),
            flush=True,
        )
        return None


def pending_resume_rows(rows, out):
    pending = []
    for row in rows:
        prior = saved_json(out / "companies" / (row["rank"] + ".json"), "receipt")
        if prior is None:
            pending.append(row)
            continue
        damaged_raw = False
        for job in prior["jobs"]:
            rawpath = job.get("raw_record_file")
            if rawpath and saved_json(out / rawpath) is None:
                damaged_raw = True
        if damaged_raw:
            pending.append(row)
            continue
        status = prior["status"]
        if any(e.get("reason") == "owner_policy_placeholder" for e in prior.get("exclusions", [])):
            pending.append(row)
            continue
        if (row["api_endpoint"] or urlsplit(row["career_url"]).hostname == "jobs.bosch.de") and status.get(
            "collection_scope"
        ) != "supplied_listing_all_countries":
            pending.append(row)
    return pending


class Transport:
    def __init__(self, out, cache_directory=None):
        self.out = out
        self.cache = Path(cache_directory) if cache_directory else out / "cache"
        self.cache.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.hosts = {}
        self.logs = []
        self.inflight = {}
        self.local = threading.local()
        self.global_slots = threading.BoundedSemaphore(12)

    def request(self, url, **kw):
        method = kw.get("method", "POST" if "json" in kw else "GET")
        key = hashlib.sha256((method + url + json.dumps(kw.get("json"), sort_keys=True)).encode()).hexdigest()
        with self.lock:
            lock = self.inflight.setdefault(key, threading.Lock())
        with lock:
            return self._request(url, **kw)

    def _request(self, url, **kw):
        method = kw.pop("method", "POST" if "json" in kw else "GET")
        key = hashlib.sha256((method + url + json.dumps(kw.get("json"), sort_keys=True)).encode()).hexdigest()
        path = self.cache / (key + ".json")
        data = saved_json(path, "cache")
        # A network outage is not a reusable HTTP response.
        if data is None or data["status"] == 0:
            host = urlsplit(url).netloc
            with self.lock:
                state = self.hosts.setdefault(host, (threading.Lock(), threading.BoundedSemaphore(2), [0.0]))
            rate_lock, host_slots, last_start = state
            with host_slots, self.global_slots:
                with rate_lock:
                    time.sleep(max(0, 0.35 - (time.monotonic() - last_start[0])))
                    last_start[0] = time.monotonic()
                if not getattr(self.local, "session", None):
                    self.local.session = requests.Session()
                    self.local.session.trust_env = False
                s = self.local.session
                try:
                    r = s.request(
                        method,
                        url,
                        timeout=(12, 35),
                        headers={
                            "User-Agent": "Runr-Employer-DryRun/1.0 (public vacancy collection)",
                            "Accept": "application/json,text/html,application/xml;q=0.9,*/*;q=0.8",
                        },
                        **{k: v for k, v in kw.items() if k not in ("timeout", "allow_redirects")},
                    )
                    if r.status_code in (500, 502, 503, 504):
                        time.sleep(2)
                        r = s.request(
                            method,
                            url,
                            timeout=(12, 35),
                            **{k: v for k, v in kw.items() if k not in ("timeout", "allow_redirects")},
                        )
                    if not r.encoding or r.encoding.lower() == "iso-8859-1":
                        r.encoding = r.apparent_encoding or "utf-8"
                    data = {
                        "url": r.url,
                        "status": r.status_code,
                        "body": r.text,
                        "at": now(),
                        "type": r.headers.get("Content-Type", ""),
                    }
                except requests.RequestException as exc:
                    data = {"url": url, "status": 0, "body": "", "at": now(), "error": type(exc).__name__}
                atomic_json(path, data)
        with self.lock:
            self.logs.append(
                {
                    "requested_url": url,
                    "method": method,
                    "resolved_url": data["url"],
                    "status": data["status"],
                    "at": data["at"],
                    "cache_key": key,
                    "error": data.get("error", ""),
                }
            )
        r = requests.Response()
        r.status_code = data["status"]
        r.url = data["url"]
        r._content = data["body"].encode("utf-8")
        r.encoding = "utf-8"
        if data["status"] == 0:
            raise requests.ConnectionError(data.get("error", "network_error"))
        if r.status_code >= 400:
            raise requests.HTTPError("HTTP_" + str(r.status_code), response=r)
        if BLOCK.search(r.text[:250000]):
            raise ValueError("access_challenge_no_bypass")
        return r


def inventory(workbook, out):
    w = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    rows = []
    for values in list(w.worksheets[0].values)[4:]:
        if not isinstance(values[0], (float, int)):
            continue
        row = {k: text(v) for k, v in zip(HEADERS, values)}
        u = row["api_endpoint"] or row["career_url"]
        platform = detect_ats(u) or (
            "eightfold"
            if (urlsplit(u).hostname or "").endswith(".eightfold.ai")
            else "public_jobposting_feed"
            if "jobs.feed.json" in u
            else "custom"
        )
        basis = "ATS host or tested feed endpoint" if platform != "custom" else "unidentified"
        cache = out / "cache" / (hashlib.sha256(("GET" + row["career_url"] + "null").encode()).hexdigest() + ".json")
        cached = saved_json(cache, "cache")
        if cached:
            body = cached.get("body", "").lower()
            if any(marker in body for marker in ("rmkcdn.successfactors.", "jobs2web.com")):
                platform = "successfactors"
                basis = "SAP vendor URLs in employer HTML"
            elif any(marker in body for marker in ("softgarden.io", "softgarden.de")):
                platform = "softgarden"
                basis = "Softgarden URLs in employer HTML"
        row["source_platform"] = platform
        row["platform_detection_basis"] = basis
        row["recommended_method"] = (
            "Workbook public API with pagination and detail"
            if row["api_endpoint"]
            else "Existing ATS router"
            if detect_ats(u)
            else "Existing JSON-LD / embedded JSON / HTML parser; render only if needed"
        )
        rows.append(row)
    assert len(rows) == 367, f"Expected 367 companies, found {len(rows)}"
    write_csv(out / "source_inventory.csv", rows)
    atomic_json(
        out / "workbook_scope.json",
        {
            "path": str(workbook),
            "sha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
            "sheets": [{"name": s.title, "rows": list(s.values)} for s in w.worksheets[1:]],
        },
    )
    return rows


def json_nodes(value):
    if isinstance(value, dict):
        yield value
        for x in value.values():
            yield from json_nodes(x)
    elif isinstance(value, list):
        for x in value:
            yield from json_nodes(x)


def extract(html, url):
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    if urlsplit(url).hostname == 'about.puma.com' and re.match(r'^/(?:en|de)/jobs/', urlsplit(url).path):
        article = soup.select_one('article.job')
        schema = next((n for n in _json_ld_values(soup) if n.get('@type') == 'JobPosting' and n.get('title')), None)
        apply = next((a for a in soup.select('a[href]')
                      if (urlsplit(a['href']).hostname or '').endswith('.myworkdayjobs.com')
                      and urlsplit(a['href']).path.rstrip('/').endswith('/apply')), None)
        if article and schema and apply:
            body = BeautifulSoup(str(article), 'lxml')
            for node in body.select('.share, .button, script, style'):
                node.decompose()
            def section(selector):
                heading = article.select_one(selector)
                row = heading.find_parent(class_='row') if heading else None
                text_node = row.select_one('.text') if row else None
                return str(text_node) if text_node else ''
            mission, talent = section('.js-job-additional'), section('.js-job-talent')
            if len(plain(mission)) >= 40 and len(plain(talent)) >= 40:
                raw = {**schema, 'url': url, 'description': str(body),
                       'responsibilities': mission, 'qualifications': talent,
                       'applicationUrl': canonical(apply['href'], url)}
                requisition = re.search(r'(?<![A-Za-z0-9])(R\d+)(?![A-Za-z0-9])', apply['href'], re.I)
                if requisition:raw['identifier'] = {'value': requisition[1].upper()}
                job = _job_from_json_ld(raw, page_url=url, raw_html='')
                return soup, [(job, raw, 'puma_job_html')]
    # adidas' public SuccessFactors board exposes location tokens, not JSON-LD.
    # Keep these source fields and the vacancy body instead of whole-page text.
    if urlsplit(url).hostname == 'jobs.adidas-group.com' and '/job/' in urlsplit(url).path:
        title = soup.select_one('.jobTitle h1, h1')
        body = soup.select_one('.jobdescription')
        apply = soup.select_one('a.apply[href*="/talentcommunity/apply/"]')
        if title and body and apply and len(plain(str(body))) >= 80:
            def token(name):
                node = soup.select_one('[data-careersite-propertyid="' + name + '"]')
                return node.get_text(' ', strip=True) if node else ''
            raw = {
                '@type': 'JobPosting', 'title': title.get_text(' ', strip=True),
                'description': str(body), 'url': url,
                'identifier': urlsplit(apply['href']).path.rstrip('/').split('/')[-1],
                'applicationUrl': canonical(apply['href'], url),
                'jobLocation': {'address': {'addressLocality': token('city'),
                                          'addressCountry': token('country')}},
            }
            return soup, [(_job_from_json_ld(raw, page_url=url, raw_html=''), raw, 'adidas_successfactors_html')]
    for item in _json_ld_values(soup):
        jobs.append((_job_from_json_ld(item, page_url=url, raw_html=""), item, "json_ld"))
    for node in soup.select('[itemscope][itemtype*="JobPosting"]'):

        def prop(name, root=node):
            el = root.select_one('[itemprop="' + name + '"]')
            return (
                (el.get("content") or el.get("datetime") or el.get("href") or el.get_text(" ", strip=True))
                if el
                else ""
            )

        raw = {
            k: prop(k)
            for k in (
                "title",
                "description",
                "datePosted",
                "validThrough",
                "employmentType",
                "workHours",
                "responsibilities",
                "qualifications",
                "skills",
                "industry",
                "jobLocationType",
            )
        }
        raw.update({"@type": "JobPosting", "url": prop("url") or url, "identifier": prop("identifier")})
        raw["hiringOrganization"] = (
            {"name": prop("name", node.select_one('[itemprop="hiringOrganization"]'))}
            if node.select_one('[itemprop="hiringOrganization"]')
            else {}
        )
        raw["jobLocation"] = {
            "address": {
                k: prop(k)
                for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")
            }
        }
        if raw["title"] and len(raw["description"]) > 80:
            jobs.append((_job_from_json_ld(raw, page_url=url, raw_html=""), raw, "microdata"))
    # The embedded adapter repeats the whole HTML parse. A complete structured
    # record for this exact detail already has the fields it can expose.
    if jobs and all(
        canonical(j.get("job_detail_url") or j.get("url")).rstrip("/") == canonical(url).rstrip("/")
        and len(plain(j.get("description"))) > 80
        for j, _, _ in jobs
    ):
        return soup, jobs
    # Exclude JSON-LD here: its richer raw record has already been retained.
    for script in soup.select('script[type="application/ld+json"]'):
        script.decompose()
    for j in extract_embedded_jobs(str(soup), url):
        jobs.append((j, dict(j), "embedded_json"))
    # Only admit HTML details with an explicit application action and substantial text.
    if not jobs and DETAIL.search(url):
        j = _job_from_html(page_url=url, html=html)
        reason = generic_employer_non_job_reason({**j, "extraction_method": "html", "apply_url": j.get("apply_link")})
        if not reason and j.get("title", "").casefold() not in (
            "stellenangebote",
            "stellenangebote finden",
            "job suche",
            "jobs suchen",
        ):
            jobs.append((j, {"labelled_fields": j.get("source_raw_payload", {}).get("labelled_fields", {})}, "html"))
    return soup, jobs


def crawl_extract(html, url):
    """Return plain data so HTML parsing can run outside the collector's GIL."""
    soup, jobs = extract(html, url)
    links = []
    if not (DETAIL.search(url) and jobs):
        for a in soup.select("a[href], iframe[src]"):
            target = canonical(a.get("href") or a.get("src"), url)
            # Siemens share links embed "JobDetail" in a query string but are
            # social widgets, not another vacancy or a pagination target.
            parsed = urlsplit(target)
            if parsed.hostname == 'jobs.siemens.com' and '/externaljobs/wechat/ShareJob' in parsed.path:
                continue
            if target:
                links.append(
                    {
                        "target": target,
                        "label": a.get_text(" ", strip=True),
                        "rel": list(a.get("rel") or []),
                        "name": a.name,
                        "pagination": a.find_parent(class_=re.compile("pagination|pager", re.I)) is not None,
                    }
                )
    return jobs, links


def parse_crawl(html, url):
    return PARSERS.submit(crawl_extract, html, url).result() if PARSERS is not None else crawl_extract(html, url)


def employer_link_allowed(target, source_urls):
    """Never expand employer collection into external general job boards."""
    host = (urlsplit(target).hostname or "").lower()
    if not host or any(
        host == b or host.endswith("." + b)
        for b in ("xing.com", "linkedin.com", "indeed.com", "indeed.de", "stepstone.de", "monster.de", "monster.com")
    ):
        return False
    hosts = {(urlsplit(u).hostname or "").lower() for u in source_urls if u}
    return host in hosts or bool(detect_ats(target))


def db_jobpostings(soup):
    """DB emits literal newlines in JSON string values; retain their wording."""
    nodes = [n for n in _json_ld_values(soup) if n.get("@type") == "JobPosting"]
    if nodes:
        return nodes
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            raw = json.loads(script.get_text(), strict=False)
        except (ValueError, TypeError):
            continue
        if isinstance(raw, dict) and raw.get("@type") == "JobPosting":
            nodes.append(raw)
    return nodes


def db_html_jobposting(soup, url):
    """Read explicit DB job text when embedded JSON has unescaped HTML quotes."""
    if urlsplit(url).hostname != "db.jobs":
        return None
    description, title = soup.select_one(".o-jobad__text"), soup.select_one("h1")
    if not description or not title:
        return None
    scripts = "\n".join(s.get_text() for s in soup.select("script"))

    def scalar(key):
        match = re.search(r'"' + re.escape(key) + r'"\s*:\s*("(?:\\.|[^"\\])*")', scripts)
        try:
            return json.loads(match[1]) if match else ""
        except ValueError:
            return ""

    return {
        "@type": "JobPosting",
        "url": url,
        "title": title.get_text(" ", strip=True),
        "description": str(description),
        "hiringOrganization": {"name": scalar("jobCompany")},
        "jobLocation": {
            "address": {
                "addressCountry": scalar("jobCountry"),
                "addressRegion": scalar("jobRegion"),
                "addressLocality": scalar("jobCity"),
            }
        },
        "datePosted": scalar("datePosted"),
        "employmentType": scalar("employmentType"),
    }


def normalized(row, job, raw, method, page, out):
    url = canonical(job.get("job_detail_url") or job.get("url") or job.get("link") or raw.get("url"), page)
    title = job.get("title") or raw.get("title")
    if not url or not title:
        return None
    uid = text(raw.get("identifier") or job.get("external_job_id") or job.get("job_id"))
    if isinstance(raw.get("identifier"), dict):
        uid = text(raw["identifier"].get("value") or raw["identifier"].get("id"))
    if uid.startswith(("http:", "https:")):
        uid = ""
    org = raw.get("hiringOrganization") or {}
    employer = org.get("name", "") if isinstance(org, dict) else text(org)
    employer = unescape(employer or text(job.get("company") or job.get("company_name")))
    loc = raw.get("jobLocation") or {}
    loc = loc[0] if isinstance(loc, list) and len(loc) == 1 else loc
    address = loc.get("address", {}) if isinstance(loc, dict) else {}
    if not isinstance(address, dict):
        address = {}
    salary = raw.get("baseSalary") or job.get("salary") or ""
    sal = salary if isinstance(salary, dict) else {}
    sv = sal.get("value") or {}
    sv = sv if isinstance(sv, dict) else {}
    tenant = urlsplit(row["api_endpoint"] or row["career_url"]).netloc + (
        "/" + (urlsplit(row["api_endpoint"]).path.split("/")[4] if "/wday/cxs/" in row["api_endpoint"] else "")
    )
    rawhash = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    rawfile = out / "raw_records" / (rawhash + ".json")
    rawfile.parent.mkdir(exist_ok=True)
    if saved_json(rawfile) is None:
        atomic_json(rawfile, raw)
    result = {
        k: row.get(k, "") for k in ("company_name", "rank", "batch", "company_website", "career_url", "scope_notes")
    }
    result.update(
        title=plain(title),
        job_id=uid,
        job_detail_url=url,
        legal_employer=employer,
        description=plain(job.get("full_description") or job.get("description") or raw.get("description")),
        responsibilities=plain(raw.get("responsibilities")),
        requirements=plain(raw.get("requirements")),
        qualifications=plain(raw.get("qualifications")),
        skills=plain(raw.get("skills")),
        seniority=text(raw.get("experienceRequirements") or job.get("experience_level")),
        employment_type=text(raw.get("employmentType") or job.get("employment_type")),
        working_hours=text(raw.get("workHours")),
        department=text(job.get("department") or raw.get("department")),
        function=text(raw.get("occupationalCategory")),
        industry=text(raw.get("industry")),
        salary=text(salary),
        salary_currency=text(sal.get("currency")),
        salary_period=text(sv.get("unitText")),
        location=text(job.get("location") or job.get("location_raw")),
        country=text(address.get("addressCountry")),
        region=text(address.get("addressRegion")),
        city=text(address.get("addressLocality")),
        postal_code=text(address.get("postalCode")),
        workplace=text(raw.get("jobLocationType") or job.get("workplace_arrangement")),
        language_requirements=text(raw.get("languageRequirements")),
        date_posted=text(raw.get("datePosted") or job.get("source_posted_at")),
        application_deadline=text(raw.get("validThrough")),
        date_collected=now(),
        source_platform=row["source_platform"],
        source_tenant=tenant,
        extraction_method=method,
        deduplication_basis="platform_tenant_stable_id" if uid else "canonical_url_fallback",
        source_page=page,
        raw_record_file=str(rawfile.relative_to(out)),
        employer_match="exact_name" if employer.casefold() == row["company_name"].casefold() else "not_verified",
        country_scope="supplied_listing_scope",
    )
    if method == "workday_cxs":
        result.update(
            date_posted=text(raw.get("datePosted")),
            date_posted_raw=text(raw.get("postedOn")),
            source_start_date=text(raw.get("startDate")),
            source_end_date=text(raw.get("endDate")),
            application_deadline=text(
                raw.get("validThrough") or raw.get("applicationDeadline") or raw.get("applicationEndDate")
            ),
        )
    return result


def export_record(record, out):
    """Apply source timestamp semantics to cached receipts from earlier passes."""
    if record.get("extraction_method") == "workday_cxs":
        raw = saved_json(out / record["raw_record_file"]) or {}
        record = {
            **record,
            "date_posted": text(raw.get("datePosted")),
            "date_posted_raw": text(raw.get("postedOn")),
            "source_start_date": text(raw.get("startDate")),
            "source_end_date": text(raw.get("endDate")),
            "application_deadline": text(
                raw.get("validThrough") or raw.get("applicationDeadline") or raw.get("applicationEndDate")
            ),
        }
    elif record.get("job_id") and " " in record["job_id"]:
        raw = saved_json(out / record["raw_record_file"]) or {}
        identifier = raw.get("identifier")
        if isinstance(identifier, dict) and not (identifier.get("value") or identifier.get("id")):
            record = {**record, "job_id": "", "deduplication_basis": "canonical_url_fallback"}
    return record


@lru_cache(maxsize=50000)
def blue_collar_evidence(title):
    """Reuse offline occupation rules; conflicting/ambiguous titles stay eligible."""
    from scripts.audit_title_collars import classify_titles, normalize_title, RULE_VERSION

    normalized_title = normalize_title(plain(title))
    professional = re.search(
        r"\b(?:\w*ingenieur\w*|engineer\w*|software\w*|developer\w*|\w*entwickler\w*|analyst\w*|scientist\w*|"
        r"buchhalt\w*|account\w*|sachbearbeit\w*|manager\w*|director\w*|head|\w*leiter\w*|\w*leitung|"
        r"planer\w*|planung\w*|consultant\w*|berater\w*|research\w*|recruit\w*|it|hr|office|"
        r"verwaltung\w*|administrat\w*|einkauf\w*|buyer\w*|procurement|controller\w*|marketing\w*|"
        r"kaufmaennisch\w*|dual\w* studium|\w*fachwirt\w*|innendienst|\w*fuehrungskraft\w*|"
        r"management|supervisor\w*|team lead\w*)\b",
        normalized_title,
    )
    manual_retail = re.search(
        r"\b(?:kassier\w*|kassentaetigkeit\w*|kassenkraft\w*|cashier\w*|warenverraeum\w*|"
        r"regalauffuell\w*|regalservice\w*|shelf (?:stock\w*|stack\w*)|stocking associate)\b",
        normalized_title,
    )
    if manual_retail and not professional:
        return {
            "reason": "explicit_manual_retail_occupation",
            "matched_terms": manual_retail[0],
            "rule_version": RULE_VERSION + "+workbook_manual_retail_v1",
        }
    rail_manual = re.search(
        r"\b(?:\w*lokfuehrer\w*|lokrangierfuehrer\w*|rangierbegleiter\w*|gleisbauer\w*|fahrzeugreiniger\w*)\b",
        normalized_title,
    )
    if rail_manual and not professional:
        return {
            "reason": "explicit_rail_manual_occupation",
            "matched_terms": rail_manual[0],
            "rule_version": RULE_VERSION + "+workbook_rail_manual_v1",
        }
    frontline_retail = re.search(
        r"\b(?:verkaeufer\w*|fachverkaeufer\w*|verkaeuferin\w*|verkauf|"
        r"(?:retail|store|shop|supermarket) (?:sales )?(?:assistant|associate|worker|colleague|crew)\w*|"
        r"sales associate|(?:kaufmann|kauffrau) im einzelhandel|ladenhilfe\w*|filialmitarbeiter\w*)\b",
        normalized_title,
    )
    # The owner explicitly excluded frontline retail sales as well. Keep
    # leadership and office/commercial qualifications; no sector-wide blacklist.
    if frontline_retail and not professional:
        return {
            "reason": "owner_frontline_retail_exclusion",
            "matched_terms": frontline_retail[0],
            "rule_version": RULE_VERSION + "+workbook_frontline_retail_v1",
        }
    result = classify_titles([plain(title)])
    # Numeric page links and generic navigation headings are not occupations.
    # The audit labels placeholders blue, but acquisition must keep following
    # those links and must not count them as excluded vacancies.
    if result["reason"] == "owner_policy_placeholder":
        return None
    if result["collar"] != "blue":
        return None
    # An occupational conflict is insufficient evidence to discard a professional
    # vacancy (e.g. Driver Software Engineer). Do not apply the audit's separate
    # historical conflict override to this collection.
    if result["white_matches"] and (professional or not result["policy_matches"]):
        return None
    matches = result.get("policy_matches", []) or result["blue_matches"]
    return {
        "reason": result["reason"],
        "matched_terms": "; ".join(dict.fromkeys(m["term"] for m in matches)),
        "rule_version": RULE_VERSION,
    }


def filter_saved_jobs(data):
    """Apply the same exclusion to earlier receipts without another network crawl."""
    kept = []
    data["status"].setdefault("records_before_role_filter", len(data["jobs"]))
    exclusions = data["exclusions"] = [
        e for e in data.get("exclusions", []) if e.get("reason") != "owner_policy_placeholder"
    ]
    known = {canonical(e["job_detail_url"]) for e in exclusions}
    for job in data["jobs"]:
        evidence = blue_collar_evidence(job["title"])
        if not evidence:
            kept.append(job)
            continue
        target = canonical(job["job_detail_url"])
        if target not in known:
            exclusions.append(
                {
                    **{k: job.get(k, "") for k in ("rank", "company_name", "title", "job_detail_url", "job_id")},
                    **evidence,
                    "stage": "saved_record",
                }
            )
            known.add(target)
    data["jobs"] = kept
    data["status"].update(
        role_scope="exclude_blue_collar_and_frontline_retail_v1",
        blue_collar_excluded=len(exclusions),
        jobs_collected=len(kept),
    )


def collect(row, t, out, probe=False, browser=False, exclude_blue_collar=False):
    result = {k: row[k] for k in ("company_name", "rank", "batch", "career_url", "source_platform", "scope_notes")}
    result.update(
        status="failed",
        jobs_collected=0,
        pages=0,
        details_failed=0,
        pagination_complete=False,
        limitation="",
        method="",
        resolved_url="",
        requires_javascript="unknown",
        collection_scope="supplied_listing_all_countries",
        role_scope="exclude_blue_collar_and_frontline_retail_v1" if exclude_blue_collar else "all_roles",
        blue_collar_excluded=0,
    )
    jobs = []
    exclusions = []
    excluded_targets = set()
    seen = set()
    maxpages = 2 if probe else min(100000, int(row.get('_max_pages', 100000)))
    result_lock = threading.Lock()
    progress = out / "progress"
    progress.mkdir(exist_ok=True)

    def checkpoint(final=False):
        snapshot = {**result, "jobs_collected": len(jobs), "updated_at": now(), "finished": final}
        path = progress / (row["rank"] + ".json")
        atomic_json(path, snapshot)

    def excluded(title, target, stage):
        if row.get('_business_candidates_only'):
            from backend.acquisition.employer_focus import review_title_candidate
            if not review_title_candidate(text(title)):
                return True
        if not exclude_blue_collar:
            return False
        target = canonical(target)
        with result_lock:
            if target and target in excluded_targets:
                return True
        evidence = blue_collar_evidence(text(title))
        if not evidence:
            return False
        with result_lock:
            if target not in excluded_targets:
                exclusions.append(
                    {
                        "rank": row["rank"],
                        "company_name": row["company_name"],
                        "title": plain(title),
                        "job_detail_url": target,
                        "stage": stage,
                        **evidence,
                    }
                )
                excluded_targets.add(target)
                result["blue_collar_excluded"] = len(exclusions)
        return True

    def add(job, raw, method, page):
        target = canonical(job.get("job_detail_url") or job.get("url") or job.get("link") or raw.get("url"), page)
        if excluded(job.get("title") or raw.get("title"), target, "detail_record"):
            return None
        record = normalized(row, job, raw, method, page, out)
        if record:
            jobs.append(record)
        return record

    def get(url, **kw):
        for attempt in range(3):
            try:
                r = t.request(url, **kw)
                break
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        with result_lock:
            result["pages"] += 1
            count = result["pages"]
        if not probe and count % 25 == 0:
            checkpoint()
        return r

    try:
        endpoint = row["api_endpoint"]
        if '/wday/cxs/' in endpoint or 'jobs.feed.json' in endpoint or detect_ats(row['career_url']) == 'personio':
            # Known public APIs/XML do not depend on a marketing page being reachable.
            # This response carries URL context only; source records still come
            # exclusively from the real API/XML requests in the branches below.
            landing = requests.Response()
            landing.url = row['career_url']
            landing.status_code = 200
            landing._content = b''
            result['landing_page_required'] = False
        else:
            landing = get(row["career_url"])
        result["resolved_url"] = landing.url
        if not endpoint and (detect_ats(landing.url) == "softgarden" or "softgarden" in landing.text.lower()):
            candidate = urljoin(landing.url, "/jobs.feed.json")
            try:
                feed = get(candidate).json()
                if (
                    any(str(x.get("@type", "")).lower() == "jobposting" for x in json_nodes(feed))
                    or feed.get("numberOfItems") == 0
                ):
                    endpoint = candidate
                    result["discovered_public_feed"] = candidate
                    row = {**row, "source_platform": "softgarden_feed"}
                    result["source_platform"] = "softgarden_feed"
            except Exception:
                pass
        if urlsplit(landing.url).hostname == 'jobs.lidl.de' and urlsplit(landing.url).path.rstrip('/') == '/suche':
            result['method'] = 'lidl_public_search_api'
            params = dict(parse_qsl(urlsplit(row['career_url']).query))
            facets = json.loads(params.get('facets', '{}'))
            general = json.loads(params.get('general', '{}'))
            general['page'] = 1
            general.setdefault('resultsPerPage', 10)
            api = urljoin(landing.url, '/api/v1/search')
            result['discovered_public_feed'] = api
            total = None; listings = {}
            while result['pages'] < maxpages:
                query = {**params, 'facets': json.dumps(facets), 'general': json.dumps(general)}
                page_url = api + '?' + urlencode(query)
                payload = get(page_url).json()
                count = int(payload['meta']['totalCount'])
                if total is None:total = count;result['source_reported_count'] = total
                if count != total:raise ValueError('lidl_total_changed_during_pagination')
                before = len(listings)
                for item in payload['jobs']:
                    uid = text(item['requisitionId']);target = canonical(item['jobDetailUrl'])
                    if urlsplit(target).hostname != 'jobs.lidl.de' or not urlsplit(target).path.startswith('/jobs/'):
                        raise ValueError('lidl_unexpected_job_url')
                    # The UI result can match secondary categories absent from
                    # employmentAreaId. Preserve the exact API query/result set.
                    if facets.get('employment_area') and item.get('employmentAreaId') not in facets['employment_area']:
                        result['primary_area_differs_from_filter'] = result.get('primary_area_differs_from_filter',0)+1
                    if uid in listings:continue
                    listings[uid] = target
                    if excluded(item['title'], target, 'lidl_api_listing'):continue
                    loc = item.get('location') or {}
                    raw = {'@type':'JobPosting','title':item['title'],'url':target,'identifier':uid,
                           'description':item.get('descResponsibilities') or '',
                           'hiringOrganization':{'name':item.get('company','')},
                           'applicationUrl':canonical(item.get('recruitingUrl') or item.get('recruitingUrlSF')),
                           'datePosted':item.get('onlineFrom'),'employmentType':item.get('contractType'),
                           'jobLocation':{'address':{'addressCountry':loc.get('country'),
                               'addressLocality':loc.get('city'),'postalCode':loc.get('zipCode')}},
                           'source_listing':item}
                    if len(plain(raw['description'])) < 150 and result['pages'] < maxpages:
                        try:
                            detail = get(target)
                            if canonical(detail.url).rstrip('/') != target.rstrip('/'):raise ValueError('lidl_detail_redirected')
                            _,found = extract(detail.text,detail.url)
                            valid = [r for _,r,method in found if method=='json_ld'
                                     and ' '.join(plain(r.get('title')).split()).casefold()==' '.join(plain(item['title']).split()).casefold()
                                     and len(plain(r.get('description')))>150]
                            if valid:raw['description'] = valid[0]['description']
                        except Exception:
                            pass
                    if len(plain(raw['description'])) < 150 or not raw['applicationUrl']:
                        result['details_failed'] += 1
                        result.setdefault('missing_details',[]).append({'job_id':uid,'title':item['title'],'url':target,'application_url':raw['applicationUrl'],'reason':'Source description/application missing or incomplete'})
                        continue
                    job = _job_from_json_ld(raw,page_url=target,raw_html='')
                    record = add(job,raw,'lidl_public_search_api',page_url)
                    if record:record['application_url'] = raw['applicationUrl']
                result['unique_listings_seen'] = len(listings)
                if len(listings) == total:
                    result['pagination_complete'] = True;break
                if len(listings) > total or len(listings) == before:
                    raise ValueError('lidl_repeated_or_invalid_page_before_total')
                general['page'] += 1
                if probe:break
            result['title_scope_excluded'] = len(listings)-len(jobs)-result['details_failed']
            result['limitation'] = 'Same public API and facets/general query as the supplied UI. Source descriptions and application URLs retained when present; incomplete records reported separately.'
        elif ((urlsplit(landing.url).hostname == 'jobs.rewe-group.com' and urlsplit(landing.url).path == '/jobs/suchen')
              or (urlsplit(landing.url).hostname == 'verbund.edeka' and urlsplit(landing.url).path.rstrip('/') == '/karriere/stellenboerse')):
            rewe = urlsplit(landing.url).hostname == 'jobs.rewe-group.com'
            result['method'] = 'rewe_filtered_html' if rewe else 'edeka_filtered_html'
            parts = urlsplit(row['career_url']);params = parse_qsl(parts.query,keep_blank_values=True)
            cursor = 'index' if rewe else 'page'
            params = [(k,v) for k,v in params if k != cursor]
            listings = {};total = None;page_num = 1
            while result['pages'] < maxpages:
                page_url = urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(params+[(cursor,str(page_num))]),''))
                response = landing if page_num == 1 else get(page_url)
                soup = BeautifulSoup(response.text,'lxml');body = soup.get_text(' ',strip=True)
                pattern = r'(\d[\d.]*)\s+Job\s+Jobs insgesamt' if rewe else r'Anzahl der Suchergebnisse:\s*(\d[\d.]*)'
                match = re.search(pattern,body)
                if not match:raise ValueError('filtered_listing_missing_total')
                count = int(match[1].replace('.',''))
                if total is None:total=count;result['source_reported_count']=total
                if count != total:raise ValueError('filtered_listing_total_changed')
                cards = soup.select('a.job-search__item-content[href]') if rewe else soup.select('a[href*="/karriere/stellenboerse/stelle-"]')
                before = len(listings)
                for card in cards:
                    target=canonical(card['href'],response.url)
                    if urlsplit(target).hostname != parts.hostname:raise ValueError('filtered_listing_external_url')
                    label=card.select_one('.job-search__item-label') if rewe else card
                    listings[target]=label.get_text(' ',strip=True)
                result['unique_listings_seen']=len(listings)
                if len(listings)==total:result['pagination_complete']=True;break
                if len(listings)>total or len(listings)==before:raise ValueError('filtered_listing_repeated_or_empty_page')
                page_num+=1
                if probe:break
            selected=[(target,title) for target,title in listings.items() if not excluded(title,target,'filtered_html_listing')]
            result['title_scope_excluded']=len(listings)-len(selected);result['details_expected']=len(selected)
            remaining=max(0,maxpages-result['pages'])
            if len(selected)>remaining:
                result['limitation']='page_limit_reached';result['pagination_complete']=False
            def filtered_detail(entry):
                target,title=entry
                try:
                    response=get(target)
                    if canonical(response.url).rstrip('/')!=target.rstrip('/'):raise ValueError('filtered_detail_redirected')
                    soup,found=extract(response.text,response.url)
                    exact=[(job,raw,method) for job,raw,method in found
                           if method=='json_ld' and len(plain(raw.get('description')))>150
                           and ' '.join(plain(raw.get('title')).split()).casefold()==' '.join(plain(title).split()).casefold()]
                    if not exact:raise ValueError('filtered_detail_missing_full_jobposting')
                    apply=next((canonical(a['href'],response.url) for a in soup.select('a[href]')
                                if re.fullmatch(r'(?:Jetzt\s+)?bewerben',a.get_text(' ',strip=True),re.I)
                                and 'initiativbewerbung' not in a['href'].lower()),'')
                    if not apply:raise ValueError('filtered_detail_missing_application_action')
                    job,raw,method=exact[0]
                    # Bind only to the fetched listing vacancy, never related jobs.
                    raw={**raw,'url':target,'applicationUrl':apply}
                    job=_job_from_json_ld(raw,page_url=target,raw_html='')
                    record=add(job,raw,result['method']+'_jsonld',response.url)
                    if record:record['application_url']=apply
                except Exception:
                    with result_lock:result['details_failed']+=1
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(filtered_detail,selected[:min(2,remaining)] if probe else selected[:remaining]))
            if not result['limitation']:
                result['limitation']='Owner-supplied filters retained across all pages; full JobPosting descriptions and explicit application actions collected. Group portal covers multiple legal employers and may include student/apprentice or non-Germany roles before recurring exclusions.'
        elif urlsplit(endpoint).hostname == 'about.puma.com' and urlsplit(endpoint).path == '/dd_job_search':
            result['method'] = 'puma_public_search_api'
            params = dict(parse_qsl(urlsplit(row['career_url']).query))
            request_body = {'q': params.get('q', ''), 'area': params.get('area', 'corporate'),
                            'location': [x for x in params.get('location', '').split(',') if x]}
            listings = {};offset = 0;total = None
            while result['pages'] < maxpages:
                payload = get(endpoint, json={**request_body, 'from': offset}).json()
                hits = payload.get('hits', {})
                reported = hits.get('total', {})
                if not isinstance(reported, dict) or reported.get('relation') != 'eq':
                    raise ValueError('puma_unconfirmed_total')
                count = int(reported['value'])
                if total is None:total = count;result['source_reported_count'] = total
                if count != total:raise ValueError('puma_total_changed_during_pagination')
                items = hits.get('hits', [])
                before = len(listings)
                for hit in items:
                    item = hit['_source'];target = canonical(item.get('url'), endpoint)
                    if (urlsplit(target).hostname != 'about.puma.com'
                            or not re.match(r'^/(?:en|de)/jobs/', urlsplit(target).path)):
                        raise ValueError('puma_unexpected_job_url')
                    if request_body['area'] == 'corporate' and item.get('is_retail') not in (0, False):
                        raise ValueError('puma_corporate_filter_mismatch')
                    if request_body['location'] and not set(request_body['location']).intersection(map(str,item.get('location_tids', []))):
                        raise ValueError('puma_location_filter_mismatch')
                    listings[target] = item
                result['unique_listings_seen'] = len(listings)
                if len(listings) == total:
                    result['pagination_complete'] = True
                    break
                if len(listings) == before or not items:raise ValueError('puma_repeated_or_empty_page_before_total')
                offset += len(items)
                if probe:break
            selected = [(target,item) for target,item in listings.items()
                        if not excluded(item.get('title'),target,'puma_api_listing')]
            result['title_scope_excluded'] = len(listings)-len(selected)
            result['details_expected'] = len(selected)
            def puma_detail(entry):
                target,item = entry
                try:
                    response = get(target)
                    if canonical(response.url).rstrip('/') != target.rstrip('/'):
                        raise ValueError('puma_detail_redirected')
                    found,_ = parse_crawl(response.text,response.url)
                    exact = [(j,raw,method) for j,raw,method in found
                             if method == 'puma_job_html' and canonical(j.get('job_detail_url') or j.get('url')).rstrip('/') == target.rstrip('/')]
                    if not exact:raise ValueError('puma_missing_full_job_sections')
                    job,raw,method = exact[0]
                    record = add(job,{**raw,'source_listing':item},method,response.url)
                    if record:record['application_url'] = raw['applicationUrl']
                except Exception:
                    with result_lock:result['details_failed'] += 1
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(puma_detail, selected[:2] if probe else selected))
            result['limitation'] = 'Public endpoint and JSON body used by the supplied careers page; corporate/location filters retained. Full vacancy sections and application URLs fetched from exact detail pages.'
        elif urlsplit(landing.url).hostname == "db.jobs" and "/service/search/" in urlsplit(landing.url).path:
            result["method"] = "db_server_paginated_html"
            params = dict(parse_qsl(urlsplit(row["career_url"]).query))
            params.update(qli="true", itemsPerPage="50", sort="score")
            page_num = 0
            page_size = None
            first_total = None
            while page_num < maxpages:
                params["pageNum"] = str(page_num)
                parts = urlsplit(row["career_url"])
                page_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
                response = get(page_url)
                soup = BeautifulSoup(response.text, "lxml")
                root = soup.select_one("#resultItems[data-hits]")
                if root is None:
                    raise ValueError("db_missing_listing_count")
                total = int(root["data-hits"])
                if first_total is None:
                    first_total = total
                    result["source_reported_count"] = first_total
                result["source_reported_count_end"] = total
                cards = root.select("a[data-job-id]")
                if page_size is None:
                    page_size = len(cards) or 50
                before_count = len(seen)
                fresh = []
                for card in cards:
                    uid = card["data-job-id"]
                    if uid in seen:
                        continue
                    seen.add(uid)
                    title_node = card.select_one(".m-search-hit__title-text")
                    title = title_node.get_text(" ", strip=True) if title_node else card.get("aria-label", "")
                    target = canonical(card.get("href"), response.url)
                    if not employer_link_allowed(target, [landing.url]):
                        continue
                    locations = card.select("li.m-search-hit__item")
                    base = {
                        "title": title,
                        "job_id": uid,
                        "url": target,
                        "location": locations[0].get_text(" ", strip=True) if locations else "",
                        "company": locations[1].get_text(" ", strip=True) if len(locations) > 1 else "",
                    }
                    if not excluded(title, target, "db_listing"):
                        fresh.append(base)

                def db_detail(base):
                    try:
                        detail = get(base["url"])
                        detail_soup = BeautifulSoup(detail.text, "lxml")
                        nodes = db_jobpostings(detail_soup)
                        if not nodes:
                            html_record = db_html_jobposting(detail_soup, detail.url)
                            nodes = [html_record] if html_record else []
                        if not nodes:
                            raise ValueError("db_detail_missing_jobposting")
                        raw = nodes[0]
                        job = _job_from_json_ld(raw, page_url=detail.url, raw_html="")
                        job.update(job_id=base["job_id"], url=detail.url)
                        raw = {
                            **raw,
                            "source_detail_identifier": raw.get("identifier"),
                            "identifier": {"value": base["job_id"]},
                            "source_listing": base,
                        }
                        add(job, raw, "db_server_paginated_html", page_url)
                    except Exception:
                        with result_lock:
                            result["details_failed"] += 1
                        add(base, {"source_listing": base}, "db_listing_only", page_url)

                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(db_detail, fresh[:2] if probe else fresh))
                result["unique_listings_seen"] = len(seen)
                result["listing_pages"] = page_num + 1
                if len(seen) >= first_total or (not cards and len(seen) >= total):
                    result["pagination_complete"] = len(seen) >= total and first_total == total
                    break
                if cards and len(seen) == before_count:
                    raise ValueError("db_repeated_listing_page_before_total")
                if not cards or (
                    not fresh and all(card["data-job-id"] in seen for card in cards) and len(cards) < page_size
                ):
                    result["limitation"] = "DB listing ended before first-page count; source may have changed."
                    break
                if probe:
                    break
                page_num += 1
            result["limitation"] = (
                result["limitation"]
                + " Public HTML pagination uses pageNum and the UI's 50-results option; source count checked against unique listing IDs. Supplied country and legalentity filters are retained with qli=true; legal employer is preserved per vacancy and workbook association remains source-based."
            ).strip()
        elif "eightfold.ai/api/" in endpoint:
            result["method"] = "eightfold_public_api"
            offset = 0
            total = None
            parts = urlsplit(endpoint)
            params = dict(parse_qsl(parts.query))
            listing_params = dict(parse_qsl(urlsplit(row["career_url"]).query))
            for name in ("location", "query", "department", "domain"):
                if name in params and name not in listing_params and name != "domain":
                    params.pop(name)
            endpoint = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
            for _ in range(maxpages):
                parts = urlsplit(endpoint)
                query = dict(parse_qsl(parts.query))
                query.update(start=str(offset), num="100")
                page = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
                payload = get(page).json()
                items = payload.get("positions")
                if not isinstance(items, list):
                    raise ValueError("unexpected_eightfold_schema")
                total = payload.get("count")
                result["source_reported_count"] = total
                fresh = 0
                selected = []
                for raw in items[:2] if probe else items:
                    uid = text(raw.get("id"))
                    if uid in seen:
                        continue
                    seen.add(uid)
                    fresh += 1
                    if excluded(raw.get("name"), raw.get("canonicalPositionUrl"), "api_listing"):
                        continue
                    selected.append(raw)

                def fetch_eightfold_detail(raw):
                    uid = text(raw.get("id"))
                    j = {
                        "title": raw.get("name"),
                        "job_id": raw.get("ats_job_id") or uid,
                        "url": raw.get("canonicalPositionUrl"),
                        "description": raw.get("job_description"),
                        "location": raw.get("location"),
                        "department": raw.get("department"),
                        "workplace_arrangement": raw.get("work_location_option"),
                    }
                    try:
                        response = get(j["url"])
                        details, _ = parse_crawl(response.text, response.url)
                        detail = next((x for x in details if x[2] == "json_ld"), None)
                        if detail:
                            dj, dr, _ = detail
                            j = {**j, **dj, "job_id": j["job_id"]}
                            raw = {
                                **dr,
                                "identifier": {"value": j["job_id"]},
                                "source_api_position": raw,
                                "source_detail_record": dr,
                            }
                    except Exception:
                        with result_lock:
                            result["details_failed"] += 1
                    add(j, raw, "eightfold_public_api", page)

                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(fetch_eightfold_detail, selected))
                offset += len(items)
                if total is not None and offset >= int(total):
                    result["pagination_complete"] = True
                    break
                if not items or not fresh:
                    raise ValueError("eightfold_empty_or_repeated_page_before_total")
                if probe:
                    break
            result["limitation"] = (
                "All countries on supplied listing; workbook Germany test query removed. Legal employer remains source-provided."
            )
        elif "/wday/cxs/" in endpoint:
            result["method"] = "workday_cxs"
            body = {"appliedFacets": {}, "searchText": "", "limit": 20, "offset": 0}
            listing_params = dict(parse_qsl(urlsplit(row["career_url"]).query))
            for name, value in listing_params.items():
                if name in ("q", "searchText"):
                    body["searchText"] = value
                elif name not in ("source", "locationHierarchy1", "locationHierarchy2"):
                    body["appliedFacets"][name] = value.split(",")
            total = None
            count = 0
            listpages = 0
            while listpages < maxpages:
                payload = get(endpoint, json=dict(body)).json()
                listings = payload.get("jobPostings")
                listpages += 1
                if not isinstance(listings, list):
                    raise ValueError("unexpected_workday_schema")
                if listpages == 1:
                    total = payload.get("total")
                result["source_reported_count"] = total
                if not listings and total and count < int(total):
                    raise ValueError("workday_empty_page_before_total")
                fresh = 0
                details = []
                for item in listings:
                    p = item.get("externalPath", "")
                    if not p or p in seen:
                        continue
                    seen.add(p)
                    fresh += 1
                    count += 1
                    detail_api = endpoint[:-5] + p
                    detail_url = urljoin(landing.url.rstrip("/") + "/", p.lstrip("/"))
                    if excluded(item.get("title"), detail_url, "api_listing"):
                        continue
                    if probe and len(jobs) >= 2:
                        continue
                    details.append((item, p))

                def fetch_detail(pair):
                    item, p = pair
                    detail_api = endpoint[:-5] + p
                    detail_url = urljoin(landing.url.rstrip("/") + "/", p.lstrip("/"))
                    try:
                        detail = get(detail_api).json()
                        info = detail.get("jobPostingInfo", {})
                        if not info:
                            raise ValueError("missing_jobPostingInfo")
                        raw = {
                            **info,
                            "hiringOrganization": detail.get("hiringOrganization") or {},
                            "source_listing": item,
                            "source_detail": detail,
                        }
                        j = {
                            "title": info.get("title"),
                            "job_id": info.get("jobReqId"),
                            "url": info.get("externalUrl") or detail_url,
                            "company": info.get("hiringOrganization") or "",
                            "description": info.get("jobDescription"),
                            "location": info.get("location"),
                            "employment_type": info.get("timeType"),
                            "source_posted_at": info.get("startDate"),
                            "workplace_arrangement": info.get("remoteType"),
                        }
                        record = add(j, raw, "workday_cxs", detail_api)
                        if record:
                            country = info.get("country") or {}
                            record["country"] = (
                                text(country.get("descriptor")) if isinstance(country, dict) else text(country)
                            )
                            record["application_deadline"] = text(info.get("endDate"))
                            if info.get("additionalLocations"):
                                record["location"] = text([info.get("location"), *info["additionalLocations"]])
                    except Exception:
                        with result_lock:
                            result["details_failed"] += 1

                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(fetch_detail, details[:2] if probe else details))
                # Later pages report total=0, and offsets beyond the final
                # result can reset to page one. Retain the FIRST count.
                if total is not None and int(total) > 0 and count >= int(total):
                    result["pagination_complete"] = True
                    break
                if not listings:
                    result["pagination_complete"] = total is not None and count >= int(total)
                    break
                if not fresh:
                    raise ValueError("workday_repeated_page")
                body["offset"] += len(listings)
                if probe:
                    break
            result["limitation"] = (
                "All countries on supplied listing; workbook Germany test filters removed. Legal employer remains source-provided."
            )
        elif endpoint and "jobs.feed.json" in endpoint:
            result["method"] = "public_json_feed"
            payload = get(endpoint).json()
            nodes = [x for x in json_nodes(payload) if str(x.get("@type", "")).lower() == "jobposting"]
            for raw in nodes[:2] if probe else nodes:
                add(_job_from_json_ld(raw, page_url=endpoint, raw_html=""), raw, "public_json_feed", endpoint)
            result["source_reported_count"] = len(nodes)
            declared = (
                payload.get("numberOfItems")
                if isinstance(payload, dict)
                else len(payload)
                if isinstance(payload, list)
                else None
            )
            result["pagination_complete"] = declared is not None and len(nodes) == int(declared)
            if not nodes and declared != 0:
                raise ValueError("feed_no_jobposting_schema")
        elif urlsplit(landing.url).hostname == "jobs.bosch.de":
            result["method"] = "bosch_public_api_smartrecruiters_detail"
            soup = BeautifulSoup(landing.text, "html.parser")
            state = json.loads(soup.find("script", id="__NEXT_DATA__").string)
            queries = state["props"]["pageProps"]["dehydratedState"]["queries"]
            query = next(q for q in queries if q["queryKey"][0] == "joblist")
            index = query["queryKey"][1]
            params = query["queryKey"][2]
            payload = query["state"]["data"]["pages"][0]
            all_items = []
            page = 0
            while page < maxpages:
                all_items.extend(payload["jobs"])
                result["source_reported_count"] = payload["totalHits"]
                nxt = payload.get("nextPage")
                if nxt is None:
                    result["pagination_complete"] = len(all_items) == int(payload["totalHits"])
                    break
                if probe:
                    break
                page = int(nxt)
                endpoint = "https://jobs.bosch.de/api/filter/query?" + urlencode(
                    {
                        "indexName": index,
                        "page": page,
                        "q": params.get("searchQuery", ""),
                        "filter": quote(json.dumps(params.get("filter", {}), separators=(",", ":")), safe=""),
                    }
                )
                payload = get(endpoint).json()
            result["other_legal_employer_records_excluded"] = 0

            def fetch_bosch_detail(wrapped):
                data = wrapped["data"]
                target = canonical(data.get("applicationUrl"))
                if excluded(data.get("title"), target, "api_listing"):
                    return
                try:
                    if "/BoschGroup/" in target and data.get("idFS"):
                        detail_url = "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/" + text(
                            data["idFS"]
                        )
                        raw = get(detail_url).json()
                        sections = raw.get("jobAd", {}).get("sections", {})
                        desc = "\n\n".join(text(s.get("text")) for s in sections.values() if isinstance(s, dict))
                        raw = {
                            **raw,
                            "description": desc,
                            "hiringOrganization": {"name": data["company"]},
                            "source_listing": data,
                            "responsibilities": sections.get("jobDescription", {}).get("text", ""),
                            "qualifications": sections.get("qualifications", {}).get("text", ""),
                        }
                        j = {
                            "title": raw.get("name") or data.get("title"),
                            "job_id": data["idFS"],
                            "url": target,
                            "description": desc,
                            "location": data.get("cityState"),
                            "company": data.get("company"),
                            "employment_type": data.get("employmentType"),
                            "experience_level": data.get("entryLevel"),
                            "department": data.get("businessUnit"),
                            "workplace_arrangement": data.get("remote"),
                            "source_posted_at": data.get("postingDate"),
                        }
                        record = add(j, raw, "bosch_public_api_smartrecruiters_detail", detail_url)
                        if record:
                            record.update(
                                country=text(data.get("country")),
                                region=text(data.get("state")),
                                city=text(data.get("city")),
                                postal_code=text(data.get("zipCode")),
                            )
                    else:
                        response = get(target)
                        found, _ = parse_crawl(response.text, response.url)
                        for j, raw, method in found:
                            add(j, raw, "bosch_public_api_" + method, response.url)
                        if not found:
                            with result_lock:
                                result["details_failed"] += 1
                except Exception:
                    with result_lock:
                        result["details_failed"] += 1

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(fetch_bosch_detail, all_items[:2] if probe else all_items))
            result["limitation"] = (
                "All portal employers retained with source legal employer; workbook association is not an exact legal-employer claim."
            )
        elif (
            detect_ats(landing.url)
            in ("workday", "personio", "recruitee", "smartrecruiters", "greenhouse", "lever", "ashby")
            and not endpoint
        ):
            result["method"] = "existing_ats_router"
            snap = fetch_ats_snapshot(
                landing.url,
                detect_ats(landing.url),
                requester=t.request,
                enabled=True,
                max_pages=2 if probe else 1000,
                max_requests=2 if probe else 1000,
                page_size=100,
            )

            def fill_ats_detail(j):
                if excluded(j.get("title"), j.get("job_detail_url") or j.get("url") or j.get("link"), "ats_listing"):
                    return
                if len(plain(j.get("full_description") or j.get("description"))) < 150:
                    target = canonical(j.get("job_detail_url") or j.get("url") or j.get("link"), landing.url)
                    try:
                        response = get(target)
                        found, _ = parse_crawl(response.text, response.url)
                        details = [
                            x
                            for x in found
                            if canonical(x[0].get("job_detail_url") or x[0].get("url")).rstrip("/")
                            == target.rstrip("/")
                        ]
                        if details:
                            for detail, raw, method in details:
                                add(detail, raw, "existing_ats_router_detail_" + method, response.url)
                            return
                    except Exception:
                        pass
                    with result_lock:
                        result["details_failed"] += 1
                add(j, j.get("source_raw_payload") or j, "existing_ats_router", landing.url)

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(fill_ats_detail, snap.get("jobs", [])))
            result["pagination_complete"] = bool(snap.get("complete_snapshot"))
            result["limitation"] = text(snap.get("stop_reason") or snap.get("warnings"))
        else:
            result["method"] = "json_ld_embedded_html"
            queue = [(landing.url, landing, 0)]
            detail_queue = []
            listing_pages = 0
            listing_signatures = set()
            evidence = canonical(row["evidence_url"])
            if evidence and evidence != canonical(landing.url):
                detail_queue.append((evidence, None, 0))
            while queue or detail_queue:
                if result["pages"] >= maxpages:
                    result["limitation"] = "page_limit_reached"
                    break
                if not queue:
                    batch = []
                    batch_urls = set()
                    while detail_queue and len(batch) < min(4, maxpages - result["pages"]):
                        candidate = detail_queue.pop(0)
                        if (
                            candidate[0] not in seen
                            and candidate[0] not in batch_urls
                            and candidate[0] not in excluded_targets
                        ):
                            batch.append(candidate)
                            batch_urls.add(candidate[0])

                    def fetch_html(candidate):
                        url, response, depth = candidate
                        try:
                            return (url, response or get(url), depth)
                        except Exception:
                            with result_lock:
                                result["details_failed"] += 1
                            return None

                    with ThreadPoolExecutor(max_workers=4) as pool:
                        queue.extend(x for x in pool.map(fetch_html, batch) if x)
                    if not queue:
                        continue
                url, response, depth = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    response = response or get(url)
                except Exception:
                    result["details_failed"] += 1
                    continue
                found, links = parse_crawl(response.text, response.url)
                for j, raw, method in found:
                    # Listing JSON can lack descriptions: queue actual job details.
                    target = canonical(j.get("job_detail_url") or j.get("url"), response.url)
                    if not employer_link_allowed(
                        target, [landing.url, row["company_website"], row["evidence_url"], response.url]
                    ):
                        result["external_links_skipped"] = result.get("external_links_skipped", 0) + 1
                        continue
                    if excluded(j.get("title") or raw.get("title"), target, "structured_listing"):
                        continue
                    if target and target != canonical(response.url) and len(plain(j.get("description", ""))) < 150:
                        detail_queue.append((target, None, depth + 1))
                    else:
                        add(j, raw, method, response.url)
                is_detail = bool(DETAIL.search(response.url))
                if not is_detail:
                    listing_pages += 1
                if is_detail and found:
                    continue
                detail_links = {a["target"] for a in links if a["name"] == "a" and DETAIL.search(a["target"])}
                has_listing = bool(detail_links or found)
                if not is_detail and detail_links:
                    signature = tuple(sorted(detail_links))
                    if signature in listing_signatures:
                        result["repeated_listing_pages"] = result.get("repeated_listing_pages", 0) + 1
                        continue
                    listing_signatures.add(signature)
                for a in links:
                    target = a["target"]
                    if not target or target in seen:
                        continue
                    if not employer_link_allowed(
                        target, [landing.url, row["company_website"], row["evidence_url"], response.url]
                    ):
                        result["external_links_skipped"] = result.get("external_links_skipped", 0) + 1
                        continue
                    label = a["label"]
                    p = urlsplit(target)
                    if re.search(r"/apply(?:/|$)|/login|/bewerb(?:en|ung)", p.path, re.I):
                        continue
                    same = p.netloc == urlsplit(response.url).netloc
                    rel = a["rel"]
                    explicit_pagination = a["pagination"]
                    same_path = p.path.rstrip("/") == urlsplit(response.url).path.rstrip("/")
                    if same and (
                        (explicit_pagination and same_path)
                        or (
                            same_listing_scope(target, response.url)
                            and (
                                "next" in rel
                                or NEXT.match(label)
                                or (not is_detail and re.search(r"(startrow|offset|page)=\d+", p.query, re.I))
                            )
                        )
                    ):
                        queue.append((target, None, depth))
                    elif DETAIL.search(target):
                        if not excluded(label, target, "listing_link"):
                            detail_queue.append((target, None, depth + 1))
                    elif (
                        not has_listing
                        and depth < 2
                        and (CAREER.search(label) or a["name"] == "iframe")
                        and (same or detect_ats(target))
                    ):
                        queue.append((target, None, depth + 1))
                if probe and (len(jobs) >= 2 or result["pages"] >= 2):
                    break
            if not result["limitation"]:
                result["limitation"] = "Static links exhausted; completeness not proven for custom/JavaScript listings."
            if not jobs and not exclusions:
                result["requires_javascript"] = "suspected"
                if browser:
                    with BROWSER_SLOTS:
                        snap = fetch_browser_snapshot(
                            landing.url,
                            max_job_links=2 if probe else 100,
                            timeout_seconds=20,
                            max_requests=8 if probe else 200,
                            retry_attempts=0,
                        )
                    result["browser_status"] = snap.get("status")
                    result["requires_javascript"] = "attempted"
                    for j in snap.get("jobs", []):
                        target = canonical(j.get("job_detail_url") or j.get("url"), landing.url)
                        if not target:
                            continue
                        if excluded(j.get("title"), target, "browser_listing"):
                            continue
                        try:
                            response = get(target)
                            found, _ = parse_crawl(response.text, response.url)
                            for detail, raw, method in found:
                                add(detail, raw, "browser_discovery_" + method, response.url)
                        except Exception:
                            result["details_failed"] += 1
                    result["limitation"] += " Browser fallback is bounded; dynamic pagination unproven."
        result["jobs_collected"] = len(jobs)
        result["status"] = (
            "complete"
            if result["pagination_complete"] and not result["details_failed"]
            else "partial"
            if jobs or exclusions
            else "zero_unproven"
        )
        if probe:
            result["status"] = "probe_records" if jobs else "probe_no_records"
            result["pagination_complete"] = False
    except Exception as e:
        message = str(e)
        result["status"] = (
            "blocked" if any(x in message for x in ("HTTP_403", "HTTP_429", "HTTP_451", "challenge")) else "failed"
        )
        result["error"] = type(e).__name__ + ": " + message[:180]
        result["jobs_collected"] = len(jobs)
        if jobs:
            result["status"] = "partial"
    folder = out / ("probe" if probe else "companies")
    folder.mkdir(exist_ok=True)
    atomic_json(folder / (row["rank"] + ".json"), {"status": result, "jobs": jobs, "exclusions": exclusions})
    if not probe:
        checkpoint(final=True)
    print(
        json.dumps(
            {k: result.get(k) for k in ("rank", "company_name", "status", "jobs_collected", "pages", "error")},
            ensure_ascii=True,
        ),
        flush=True,
    )
    return result, jobs


def main():
    global PARSERS
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=["inventory", "check", "probe", "run", "export", "validate"])
    p.add_argument("--workbook", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--cache-directory", type=Path, help="Reuse HTTP responses while saving results in a separate output directory."
    )
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--browser", action="store_true")
    p.add_argument("--ranks", default="")
    p.add_argument("--resume", action="store_true")
    p.add_argument(
        "--exclude-blue-collar",
        action="store_true",
        help="Skip deterministic blue-collar and frontline retail titles before details; retain managers, office and unresolved roles.",
    )
    args = p.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"stage": args.stage, "startup": "loading_workbook_and_source_inventory"}), flush=True)
    rows = inventory(args.workbook, out)
    if args.stage == "inventory":
        return
    if args.stage == "validate":
        validate(out)
        return
    t = Transport(out, args.cache_directory)
    if args.stage == "check":

        def check(row):
            result = {
                k: row[k] for k in ("company_name", "rank", "batch", "career_url", "api_endpoint", "source_platform")
            }
            try:
                r = t.request(row["career_url"])
                soup, found = extract(r.text, r.url)
                result.update(
                    http_status=r.status_code,
                    resolved_url=r.url,
                    redirected=canonical(r.url) != canonical(row["career_url"]),
                    page_title=soup.title.get_text(" ", strip=True) if soup.title else "",
                    structured_jobs_on_page=len(found),
                    status="job_records_present" if found else "reachable_listing_not_proven",
                    checked_at=now(),
                )
            except Exception as exc:
                result.update(status="failed_or_blocked", error=str(exc)[:180], checked_at=now())
            print(json.dumps({k: result.get(k) for k in ("rank", "status", "http_status")}), flush=True)
            return result

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(check, rows))
        write_csv(out / "source_url_checks.csv", results)
        write_csv(out / "check_requests.csv", t.logs)
        return
    if args.stage != "export":
        chosen = rows
        if args.stage == "probe":
            chosen = []
            keys = set()
            for r in rows:
                key = (
                    "workday"
                    if "/wday/cxs/" in r["api_endpoint"]
                    else "feed"
                    if "jobs.feed.json" in r["api_endpoint"]
                    else r["extraction_notes"]
                )
                if key not in keys:
                    keys.add(key)
                    chosen.append(r)
            chosen = chosen[:20]
        if args.ranks:
            chosen = [r for r in rows if r["rank"] in args.ranks.split(",")]
        if args.resume and args.stage == "run":
            print(json.dumps({"startup": "checking_saved_company_results_and_raw_evidence"}), flush=True)
            chosen = pending_resume_rows(chosen, out)
        print(json.dumps({"stage": args.stage, "companies_queued": len(chosen), "workers": args.workers}), flush=True)
        with ProcessPoolExecutor(max_workers=4) if args.stage == "run" else nullcontext() as parsers:
            PARSERS = parsers
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [
                    pool.submit(collect, r, t, out, args.stage == "probe", args.browser, args.exclude_blue_collar)
                    for r in chosen
                ]
                for f in as_completed(futures):
                    f.result()
            PARSERS = None
        write_csv(out / (args.stage + "_requests.csv"), t.logs)
    folder = out / ("probe" if args.stage == "probe" else "companies")
    statuses = []
    jobs = []
    associations = []
    exclusions = []
    row_by_rank = {r["rank"]: r for r in rows}
    for path in sorted(folder.glob("*.json"), key=lambda p: int(p.stem)):
        data = saved_json(path, "receipt")
        if data is None:
            continue
        if args.exclude_blue_collar:
            filter_saved_jobs(data)
        exclusions.extend(data.get("exclusions", []))
        data["jobs"] = [export_record(j, out) for j in data["jobs"]]
        status = data["status"]
        source = row_by_rank[status["rank"]]
        status["source_platform"] = source["source_platform"]
        status["platform_detection_basis"] = source["platform_detection_basis"]
        for j in data["jobs"]:
            j["source_platform"] = source["source_platform"]
        if (
            status["source_platform"] == "workday"
            and status.get("collection_scope") == "supplied_listing_all_countries"
            and "workday_repeated_page" in status.get("error", "")
            and not status.get("details_failed")
            and status.get("records_before_role_filter", len(data["jobs"])) == status.get("source_reported_count")
        ):
            status.update(
                status="complete",
                pagination_complete=True,
                boundary_behavior=status.pop("error"),
                completion_evidence="First-page count matched every collected listing; out-of-range offset reset to page one.",
            )
        statuses.append(status)
        status["unique_jobs_collected"] = len(deduplicate(data["jobs"])[0])
        for j in data["jobs"]:
            associations.append(
                {
                    k: j[k]
                    for k in (
                        "company_name",
                        "rank",
                        "batch",
                        "job_id",
                        "job_detail_url",
                        "source_platform",
                        "source_tenant",
                        "employer_match",
                    )
                }
            )
            jobs.append(j)
    jobs, dup = deduplicate(jobs)
    prefix = "probe_" if args.stage == "probe" else ""
    write_csv(out / (prefix + "jobs.csv"), jobs, FIELDS)
    write_csv(out / (prefix + "source_status.csv"), statuses)
    write_csv(out / (prefix + "excluded_blue_collar_jobs.csv"), exclusions)
    unique_associations = list({json.dumps(a, sort_keys=True): a for a in associations}.values())
    write_csv(out / (prefix + "job_company_associations.csv"), unique_associations)
    summary = {
        "at": now(),
        "companies_attempted": len(statuses),
        "companies_with_jobs": sum(s["jobs_collected"] > 0 for s in statuses),
        "complete_sources": sum(s["status"] == "complete" for s in statuses),
        "failed_or_blocked": sum(s["status"] in ("failed", "blocked") for s in statuses),
        "zero_unproven": sum(s["status"] == "zero_unproven" for s in statuses),
        "jobs": len(jobs),
        "role_scope": "exclude_blue_collar_and_frontline_retail_v1" if args.exclude_blue_collar else "all_roles",
        "blue_collar_exclusions": len(exclusions),
        "duplicates_removed": dup,
        "javascript_suspected_or_attempted": sum(s["requires_javascript"] != "unknown" for s in statuses),
    }
    atomic_json(out / (prefix + "summary.json"), summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
