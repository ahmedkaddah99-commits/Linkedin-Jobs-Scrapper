"""Bounded, private job imports; presentation and enrichment belong to Jobs."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from backend.application.catalog_enrichment import enrich_version
from backend.application.company_enrichment import OfficialWebsiteProvider
from backend.application.company_logo import validate_official_url
from backend.application.vps_job_descriptions import build_runr_description_rules, openrouter_generate, NEMO_MODEL
from backend.connectors.generic_jsonld import _json_ld_values, _job_from_json_ld
from backend.domain.job_filter_contract import CHOICES
from backend.domain.models import utc_now_iso

log = logging.getLogger(__name__)
FIELD_LIMITS = {'title': 200, 'company': 200, 'location': 300, 'description': 50000}


def job_url(value) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError('Enter a job URL of at most 2,048 characters.')
    try:
        url = validate_official_url(value.strip())
    except ValueError as error:
        raise ValueError('Enter a public http or https job URL.') from error
    parsed = urlsplit(url)
    return parsed._replace(netloc=parsed.netloc.lower()).geturl()


def fetch_job_page(url: str) -> str:
    body, content_type, _, _ = OfficialWebsiteProvider._fetch(url, timeout_seconds=15, max_bytes=2_000_000)
    if 'html' not in content_type.lower():
        raise ValueError('The URL does not contain a job page.')
    return body.decode('utf-8', errors='replace')


def parse_job_page(html: str, url: str) -> tuple[dict, bool]:
    soup = BeautifulSoup(html, 'html.parser')
    postings = _json_ld_values(soup)
    if len(postings) > 1:
        matching = [p for p in postings if str(p.get('url') or '').rstrip('/') == url.rstrip('/')]
        postings = matching if len(matching) == 1 else []
    if len(postings) == 1:
        raw = _job_from_json_ld(postings[0], page_url=url, raw_html='')
        organization = postings[0].get('hiringOrganization')
        company = organization.get('name', '') if isinstance(organization, Mapping) else ''
        return {'url': url, 'title': raw['title'], 'company': company,
                'location': raw['location'], 'description': BeautifulSoup(raw['description'], 'html.parser').get_text('\n', strip=True),
                'employment_type': str(raw['employment_type']).lower(),
                'work_arrangement': 'remote' if raw['workplace_arrangement'] == 'TELECOMMUTE' else ''}, True
    title = soup.select_one('h1')
    company = soup.select_one('.topcard__org-name-link, [data-testid="company-name"], .company-name')
    location = soup.select_one('.topcard__flavor--bullet, [data-testid="job-location"], .job-location')
    content = soup.select_one('.show-more-less-html__markup, [data-testid="job-description"], .job-description, #job-description, [itemprop="description"], article, main')
    for element in soup.select('script, style, nav, footer, noscript, form'):
        element.decompose()
    description = (content or soup).get_text('\n', strip=True)
    return {'url': url, 'title': title.get_text(' ', strip=True) if title else '',
            'company': company.get_text(' ', strip=True) if company else '',
            'location': location.get_text(' ', strip=True) if location else '',
            'description': description[:50000]}, False


def validate_fields(fields: Mapping, *, structured_job: bool = False) -> dict:
    result = {}
    for field, limit in FIELD_LIMITS.items():
        value = fields.get(field, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'{field.capitalize()} must be text of at most {limit:,} characters.')
        result[field] = value.strip()
    if len(result['title']) < 2 or len(result['description']) < 100:
        raise ValueError('Add a job title and a job description of at least 100 characters.')
    text = result['description'].casefold()
    signals = (
        r'responsibilit|duties|aufgaben|tätigkeit|what you.ll do',
        r'qualifications?|requirements?|experience|erfahrung|anforderung|profil',
        r'full.time|part.time|employment|salary|benefits|bewerb|apply|position|stelle|job|hiring',
    )
    if not structured_job and sum(bool(re.search(pattern, text)) for pattern in signals) < 2:
        raise ValueError('This does not appear to be a job posting. Add the job responsibilities and requirements.')
    for field, choice in (('employment_type', 'employmentType'), ('work_arrangement', 'workArrangement'), ('experience_level', 'experienceLevel')):
        value = fields.get(field) or ''
        if not isinstance(value, str) or value not in {'', *(item[0] for item in CHOICES[choice])}:
            raise ValueError(f'Choose a valid {field.replace("_", " ")}.')
        result[field] = value
    return result


def build_row(user_id: str, url: str, fields: dict) -> dict:
    digest = hashlib.sha256((user_id + '\n' + url).encode()).hexdigest()[:24]
    content_hash = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    job_id = 'import_' + digest
    now = utc_now_iso()
    return {'canonical_job_id': job_id, 'company': fields['company'], 'title': fields['title'],
            'location': fields['location'], 'version_location': fields['location'],
            'description': fields['description'], 'canonical_url': url, 'apply_url': url,
            'current_version_id': job_id + '_' + content_hash[:12], 'content_hash': content_hash,
            'version_number': 1, 'version_payload_json': {**fields, 'job_detail_url': url},
            'source_ats': urlsplit(url).hostname, 'lifecycle_state': 'active',
            'first_seen_at': now, 'last_seen_at': now, 'last_verified_at': now,
            'imported_by': user_id, 'external_job': True}


def import_job(service, user_id: str, payload: Mapping, *, plan_id: str) -> dict:
    service._assert_catalog_access(user_id)
    url = job_url(payload.get('url'))
    existing = service.store.find_job_by_url(user_id, url)
    if existing and not existing.get('external_job'):
        # Keep a private snapshot, including already generated catalog output.
        # Its private identity survives retirement of the published posting.
        row = {**existing, 'canonical_job_id': 'import_' + hashlib.sha256((user_id + '\n' + url).encode()).hexdigest()[:24],
               'catalog_job_id': existing['canonical_job_id'], 'external_job': True, 'imported_by': user_id,
               'external_description': service._description_intelligence(existing)}
        service.store.save_external_job_row(user_id, url, row)
        return {'state': 'available', 'job': service.detail(user_id, row['canonical_job_id'], plan_id=plan_id)}
    if existing and not payload.get('retry_enrichment'):
        return {'state': 'available', 'job': service.detail(user_id, existing['canonical_job_id'], plan_id=plan_id)}
    manual = payload.get('manual') is True
    structured = False
    fields = {'url': url}
    if manual:
        fields.update(validate_fields(payload))
    service.store.reserve_external_job_import(user_id)
    if existing:
        source_fields = existing.get('version_payload_json') or {}
        if isinstance(source_fields, str):
            source_fields = json.loads(source_fields)
        fields.update(source_fields)
        for key in FIELD_LIMITS:
            fields.setdefault(key, existing.get(key) or '')
        structured = True
    elif not manual:
        try:
            fields, structured = parse_job_page(fetch_job_page(url), url)
            fields = {**fields, **validate_fields(fields, structured_job=structured)}
        except Exception as error:
            log.info('External job fetch unavailable (%s)', type(error).__name__)
            message = 'Unable to fetch this job from the URL. Complete the job details below.'
            if isinstance(error, ValueError) and fields.get('description'):
                message = 'This page could not be recognized as a job posting. Check the link or enter the job details below.'
            return {'state': 'manual_required', 'message': message, 'fields': {
                key: str(fields.get(key) or '')[:limit] for key, limit in {'url': 2048, **FIELD_LIMITS}.items()}}
    row = build_row(user_id, url, fields)
    row['enrichment_state'] = 'available'
    if existing:
        row['filter_json'] = existing.get('filter_json')
        row['external_description'] = existing.get('external_description')
    generate = lambda prompt: openrouter_generate(prompt, model=NEMO_MODEL, timeout=40, max_tokens=8192)
    for stage in ('filters', 'description'):
        if stage == 'filters' and row.get('filter_json'):
            continue
        if stage == 'description' and (row.get('external_description') or {}).get('provider') == 'openrouter':
            continue
        try:
            output = enrich_version({**row, 'description_ready': stage == 'filters', 'filters_ready': stage == 'description'}, generate)
            if stage == 'filters':
                filters = dict(output['filters'])
                if isinstance(filters.get('work_arrangement'), list):
                    filters['work_arrangement'] = next(iter(filters['work_arrangement']), '')
                row['filter_json'] = filters
            else:
                row['external_description'] = output['description']
        except Exception as error:
            log.warning('External job %s enrichment unavailable (%s)', stage, type(error).__name__)
            row['enrichment_state'] = 'unavailable'
    if not row.get('external_description'):
        row['external_description'] = build_runr_description_rules(row)
    saved = service.store.save_external_job_row(user_id, url, row)
    return {'state': 'available', 'job': service.detail(user_id, saved['canonical_job_id'], plan_id=plan_id)}
