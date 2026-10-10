"""Read-only aggregate pipeline telemetry; no job/company payloads leave the host.

Runs independently of producers. Failed sections retain their last good snapshot
with up=0 and its original timestamp, never replacing unavailable data with zero.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time
import urllib.request
from collections import Counter
from contextlib import closing
from pathlib import Path

OUTPUT = Path('/var/lib/runr/observability')
FIELDS = ('website', 'domain', 'industry', 'company_size', 'headquarters', 'linkedin_company_id',
          'linkedin_company_url', 'companyenrich_id', 'founded_year', 'company_type', 'type',
          'revenue', 'revenue_range', 'description', 'logo')
REASONS = {'budget_exhausted', 'card_detail_alias_pending_verification', 'partial_source_coverage',
           'missing_company_fields', 'missing_required_fields', 'ownership_unverified',
           'invalid_apply_url', 'company_enrichment_required', 'missing_apply_url',
           'identity_unresolved', 'company_identity_unresolved'}
MANIFEST_REASONS = {'canonical_id_backfill_pending_approval', 'url_missing', 'numeric_linkedin_id_missing',
    'numeric_id_confidence_not_positive', 'numeric_id_evidence_status_not_verified:unresolved',
    'linkedin_url_missing_or_invalid', 'numeric_id_evidence_status_not_verified:invalid_linkedin_url',
    'numeric_id_evidence_status_not_verified:missing', 'linkedin_url_id_evidence_pair_mismatch',
    'canonical_id_missing_or_placeholder', 'conflicting_ownership_unresolved', 'non_company_linkedin_page:school'}


def present(value):
    return str(value or '').strip().lower() not in {'', '//', 'unknown', 'none', 'null', 'n/a', '-'}


def reason(value):
    normalized = str(value or '').lower()
    return normalized if normalized in REASONS else ('none' if not normalized else 'other')


def metric(name, value, **labels):
    return {'name': 'runr_pipeline_' + name, 'value': value, 'labels': labels}


def render(sections, attempted_at):
    result = [f'runr_pipeline_observer_timestamp_seconds {attempted_at}']
    for section, data in sections.items():
        items = [metric('section_up', int(data['up']), section=section),
                 metric('section_timestamp_seconds', data.get('timestamp', 0), section=section),
                 metric('section_duration_seconds', data.get('duration', 0), section=section)]
        items.extend(data.get('metrics', []))
        for item in items:
            value = item['value']
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            labels = ','.join(f'{key}={json.dumps(str(val), ensure_ascii=False)}' for key, val in sorted(item['labels'].items()))
            result.append(f"{item['name']}" + ('{' + labels + '}' if labels else '') + f' {value}')
    return '\n'.join(result) + '\n'


def load_env():
    from dotenv import dotenv_values
    for path in ('/opt/runr/.env.acquisition', '/etc/runr/acquisition-catalog.env', '/etc/runr/publisher-sqlite.env'):
        for key, value in dotenv_values(path).items():
            if value is not None:
                os.environ[key] = value


def manifest_items(prefix):
    import ijson
    path = Path(os.environ.get('RUNR_ACQUISITION_MANIFEST', '/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json'))
    with path.open('rb') as stream:
        yield from ijson.items(stream, prefix)


def configuration():
    limits = {'linkedin': {'requests': ('RUNR_LINKEDIN_MAX_REQUESTS', 100), 'companies': ('RUNR_LINKEDIN_MAX_COMPANIES', 25)},
              'employer': {'requests': ('RUNR_EMPLOYER_MAX_REQUESTS', 10), 'companies': ('RUNR_EMPLOYER_MAX_COMPANIES', 10)},
              'publisher': {'source_rows': ('RUNR_PUBLISHER_SOURCE_ROW_BATCH_SIZE', 250)}}
    items = [metric('configured_limit', int(os.environ.get(key, default)), source=source, limit=limit)
             for source, fields in limits.items() for limit, (key, default) in fields.items()]
    counts = next(manifest_items('counts'))
    for key in ('input_rows', 'blocked_entities', 'mapped_entities'):
        if key in counts:
            items.append(metric('manifest_records', counts[key], status=key))
    for source, key in (('linkedin', 'linkedin_tasks'), ('employer', 'employer_tasks')):
        items.append(metric('manifest_companies', counts[key], source=source))
    reasons = Counter()
    for row in manifest_items('rows.item'):
        for code in row.get('exclusion_reasons', []):
            reasons[code if code in MANIFEST_REASONS else 'other'] += 1
    items += [metric('manifest_exclusions', n, reason=code) for code, n in reasons.items()]
    return items


def company_summary(companies, careers, eligible):
    counts = Counter()
    fields = Counter()
    cohorts = Counter()
    for row in companies:
        cid = row['company_id']
        flags = {field: present(row.get('fields_' + field)) or present(row.get('additional_fields_' + field)) for field in FIELDS}
        flags['name'] = present(row['canonical_name'])
        flags['logo'] |= present(row['logo_object_key']) or present(row['logo_source_url'])
        flags['career_url'] = cid in careers
        flags['logo_verified_timestamp'] = present(row['logo_verified_at'])
        ready = all(flags[field] for field in ('name', 'website', 'industry', 'company_size', 'headquarters', 'logo'))
        counts['all'] += 1
        counts['core_populated' if ready else 'core_incomplete'] += 1
        for field, populated in flags.items():
            fields[field] += populated
        for source in ('linkedin', 'employer'):
            in_manifest = cid in eligible[source]
            cohorts[(source, 'core_populated' if ready else 'core_incomplete', 'included' if in_manifest else 'not_in_manifest')] += 1
        if ready and flags['linkedin_company_id']:
            counts['core_with_linkedin_id'] += 1
            counts['core_linkedin_id_not_in_manifest'] += cid not in eligible['linkedin']
        counts['core_with_career_url'] += ready and flags['career_url']
    return ([metric('companies', value, cohort=key) for key, value in counts.items()]
            + [metric('company_field_populated', fields[field], field=field) for field in (*FIELDS, 'name', 'career_url', 'logo_verified_timestamp')]
            + [metric('company_source_cohort', value, source=source, readiness=readiness, eligibility=eligibility)
               for (source, readiness, eligibility), value in cohorts.items()])


def company_flags_sql():
    def populated(expression):
        return f"LOWER(TRIM(CAST(COALESCE({expression},'') AS TEXT))) NOT IN ('','//','unknown','none','null','n/a','-')"
    fields = []
    for field in FIELDS:
        expression = ' OR '.join(populated(f"json_extract(p.profile_json,'$.{section}.{field}.value')") for section in ('fields', 'additional_fields'))
        if field == 'logo':
            expression += ' OR ' + populated('p.logo_source_url') + ' OR ' + populated('p.logo_object_key')
        fields.append(f'CASE WHEN {expression} THEN 1 ELSE 0 END AS {field}')
    fields += [f"CASE WHEN {populated('c.canonical_name')} THEN 1 ELSE 0 END AS name",
               f"CASE WHEN {populated('p.logo_verified_at')} THEN 1 ELSE 0 END AS logo_verified_timestamp",
               "CASE WHEN EXISTS(SELECT 1 FROM canonical_company_urls u WHERE u.company_id=c.company_id AND u.url_type IN ('careers','ats_jobs')) THEN 1 ELSE 0 END AS career_url"]
    return ('WITH flags AS (SELECT c.company_id,' + ','.join(fields)
        + ' FROM canonical_companies c LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id),'
        + ' ready AS (SELECT *,CASE WHEN name=1 AND website=1 AND industry=1 AND company_size=1 AND headquarters=1 AND logo=1 THEN 1 ELSE 0 END AS core FROM flags) ')


def catalog():
    local = os.environ.get('DATABASE_BACKEND') == 'sqlite'
    if not local and not os.environ.get('TURSO_DATABASE_URL'):
        raise RuntimeError('remote_binding_missing')
    # Avoid backend package initializers: they import the entire application,
    # which is unnecessary overhead for a read-only observer. No migrations or
    # database initialization are permitted here.
    if local:
        target = Path(os.environ['SQLITE_DATABASE_PATH'])
        if not target.is_absolute():
            raise ValueError('SQLite observer path must be absolute')
        conn = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=5)
    else:
        import libsql
        conn = libsql.connect(database=os.environ['TURSO_DATABASE_URL'], auth_token=os.environ['TURSO_AUTH_TOKEN'])
    try:
        def rows(sql, params=()):
            cursor = conn.execute(sql, params)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        import ijson
        tasks = [(task['canonical_company_id'], 'employer' if task['source'] == 'employer_site' else task['source']) for task in manifest_items('tasks.item')]
        needed = {'old-company:' + cid for cid, _ in tasks}
        crosswalk_path = Path(os.environ.get('RUNR_COMPANY_IDENTITY_CROSSWALK', '/srv/runr/state/active/company_identity_crosswalk.json'))
        with crosswalk_path.open('rb') as stream:
            crosswalk = {key: value for key, value in ijson.kvitems(stream, 'mapping_by_identity') if key in needed}
        eligible = {'linkedin': set(), 'employer': set()}
        for original, source in tasks:
            # Inputs contain only canonical IDs here. This is the project's
            # old-company crosswalk rule, not name/domain identity inference.
            cid = crosswalk.get('old-company:' + original) or original
            if source in eligible:
                eligible[source].add(cid)
        cte = company_flags_sql()
        fields = (*FIELDS, 'name', 'career_url', 'logo_verified_timestamp')
        aggregate = rows(cte + 'SELECT COUNT(*) AS total,SUM(core) AS core,SUM(core*linkedin_company_id) AS core_li,SUM(core*career_url) AS core_career,'
            + ','.join(f'SUM({field}) AS {field}' for field in fields) + ' FROM ready')[0]
        items = [metric('companies', aggregate['total'], cohort='all'), metric('companies', aggregate['core'] or 0, cohort='core_populated'),
                 metric('companies', aggregate['total'] - (aggregate['core'] or 0), cohort='core_incomplete'),
                 metric('companies', aggregate['core_li'] or 0, cohort='core_with_linkedin_id'),
                 metric('companies', aggregate['core_career'] or 0, cohort='core_with_career_url')]
        items += [metric('company_field_populated', aggregate[field] or 0, field=field) for field in fields]
        for source, ids in eligible.items():
            ids = sorted(ids)
            membership = 'company_id IN (' + ','.join('?' for _ in ids) + ')' if ids else '0'
            cohort_rows = rows(cte + f'SELECT core,CASE WHEN {membership} THEN 1 ELSE 0 END AS included,COUNT(*) AS n,SUM(linkedin_company_id) AS li FROM ready GROUP BY core,included', ids)
            for row in cohort_rows:
                items.append(metric('company_source_cohort', row['n'], source=source,
                    readiness='core_populated' if row['core'] else 'core_incomplete', eligibility='included' if row['included'] else 'not_in_manifest'))
                if source == 'linkedin' and row['core'] and not row['included']:
                    items.append(metric('companies', row['li'] or 0, cohort='core_linkedin_id_not_in_manifest'))
        for field, sql in (
            ('selected_primary_homepage', "SELECT COUNT(DISTINCT company_id) AS n FROM canonical_company_urls WHERE url_type='homepage' AND selected_primary=1"),
            ('provenance_url', "SELECT COUNT(*) AS n FROM canonical_companies WHERE TRIM(COALESCE(provenance_url,''))<>''"),
            ('company_profile', 'SELECT COUNT(*) AS n FROM canonical_company_profiles')):
            items.append(metric('company_field_populated', rows(sql)[0]['n'], field=field))
        for row in rows('SELECT lifecycle_state,COUNT(*) AS n FROM canonical_jobs GROUP BY lifecycle_state'):
            state = row['lifecycle_state'] if row['lifecycle_state'] in {'active', 'closed', 'stale', 'unknown'} else 'other'
            items.append(metric('catalog_jobs', row['n'], lifecycle=state))
        quality = rows("""SELECT COUNT(*) AS jobs,
            SUM(CASE WHEN j.lifecycle_state='active' THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN p.logo_source_url<>'' OR p.logo_object_key<>'' THEN 1 ELSE 0 END) AS logo_reference,
            SUM(CASE WHEN v.apply_url<>'' THEN 1 ELSE 0 END) AS raw_apply_url,
            SUM(CASE WHEN json_extract(v.payload_json,'$.application_destination.status')='verified' THEN 1 ELSE 0 END) AS verified_destination
            FROM acquisition_publication_jobs a JOIN acquisition_publication_head h ON h.head_id=1 AND h.publication_id=a.publication_id
            JOIN canonical_jobs j ON j.canonical_job_id=a.canonical_job_id
            LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
            LEFT JOIN canonical_company_profiles p ON p.company_id=j.company_id""")[0]
        items += [metric('published_jobs', value or 0, quality=key) for key, value in quality.items()]
        for row in rows('SELECT source,source_rowid,bootstrap_complete FROM acquisition_publisher_checkpoints'):
            source = 'employer' if row['source'] == 'employer_site' else row['source']
            source = source if source in {'linkedin', 'employer'} else 'other'
            items += [metric('import_checkpoint', row['source_rowid'], source=source),
                      metric('import_bootstrap_complete', row['bootstrap_complete'], source=source)]
        cycle = rows('SELECT cycle_id,jobs_observed,jobs_new,jobs_updated,jobs_unchanged,jobs_closed,jobs_rejected,jobs_published FROM acquisition_cycles ORDER BY scheduled_at DESC LIMIT 1')
        if cycle:
            items += [metric('publisher_latest', value, measure=key) for key, value in cycle[0].items() if key != 'cycle_id']
            for row in rows('SELECT status,COUNT(*) AS n FROM acquisition_tasks WHERE cycle_id=? GROUP BY status', (cycle[0]['cycle_id'],)):
                status = row['status'] if row['status'] in {'pending', 'running', 'completed', 'partial', 'failed', 'blocked', 'skipped'} else 'other'
                items.append(metric('publisher_tasks', row['n'], status=status))
            rejected = Counter()
            for row in rows('SELECT reason_code,COUNT(*) AS n FROM acquisition_job_rejections WHERE cycle_id=? GROUP BY reason_code', (cycle[0]['cycle_id'],)):
                rejected[reason(row['reason_code'])] += row['n']
            # Explicit zero is safe here: the rejection query completed.
            if not rejected:
                rejected['none'] = 0
            items += [metric('publisher_rejections', n, reason=code) for code, n in rejected.items()]
        inventory = rows('SELECT COUNT(*) AS jobs,MIN(last_seen_at) AS oldest FROM canonical_jobs WHERE lifecycle_state=\'active\' AND canonical_job_id NOT IN (SELECT a.canonical_job_id FROM acquisition_publication_jobs a JOIN acquisition_publication_head h ON h.head_id=1 AND h.publication_id=a.publication_id)')[0]
        items.append(metric('active_outside_head', inventory['jobs']))
        return items
    finally:
        conn.close()


def source_stores():
    items = []
    for source, key, default in (('linkedin', 'RUNR_LINKEDIN_STATE_DB', '/srv/runr/state/active/linkedin/master_linkedin_jobs_state.db'),
                                 ('employer', 'RUNR_EMPLOYER_STATE_DB', '/srv/runr/state/active/employer/master_employer_jobs_state.db')):
        path = Path(os.environ.get(key, default)).resolve(strict=True)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)) as conn:
            conn.execute('PRAGMA query_only=ON')
            # Separate queries let COUNT use a covering index and rowid use
            # the final B-tree entry, rather than scanning every job payload.
            count = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
            lastrow = conn.execute('SELECT rowid FROM jobs ORDER BY rowid DESC LIMIT 1').fetchone()
            maxrow = lastrow[0] if lastrow else 0
            items += [metric('source_jobs', count, source=source), metric('source_max_rowid', maxrow or 0, source=source)]
            if source == 'linkedin':
                latest = conn.execute('SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()
                if latest:
                    grouped = Counter()
                    for status, error, n in conn.execute('SELECT status,error_class,COUNT(*) FROM detail_attempts WHERE run_id=? GROUP BY status,error_class', latest):
                        status = status if status in {'SUCCESS', 'FAILED', 'EXCLUDED'} else 'OTHER'
                        grouped[(status.lower(), reason(error))] += n
                    items += [metric('linkedin_detail_attempts', n, status=status, reason=error) for (status, error), n in grouped.items()]
                items.append(metric('linkedin_observations', conn.execute('SELECT COUNT(*) FROM job_company_observations').fetchone()[0]))
            else:
                for status, n in conn.execute('SELECT status,COUNT(*) FROM companies GROUP BY status'):
                    status = status if status in {'completed', 'discovery_failed', 'no_jobs', 'partial', 'source_failed'} else 'other'
                    items.append(metric('employer_company_state', n, status=status))
                providers = Counter()
                for provider, n in conn.execute("SELECT json_extract(payload_json,'$.source_provider'),COUNT(*) FROM jobs GROUP BY json_extract(payload_json,'$.source_provider')"):
                    provider = provider if provider in {'generic_employer_site', 'workday', 'personio', 'softgarden', 'greenhouse', 'lever', 'recruitee', 'smartrecruiters', 'ashby'} else 'other'
                    providers[provider] += n
                items += [metric('employer_provider_jobs', n, provider=provider) for provider, n in providers.items()]
    path = Path('/srv/runr/state/enrichment/linkedin_id_resolution.sqlite3').resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        for status, n in conn.execute('SELECT status,COUNT(*) FROM url_resolution GROUP BY status'):
            items.append(metric('resolver_records', n, status=status if status in {'RESOLVED', 'UNRESOLVED'} else 'OTHER'))
        last = conn.execute('SELECT recorded_at FROM request_log ORDER BY rowid DESC LIMIT 1').fetchone()
        stamp = last[0] if last else None
        if stamp:
            from datetime import datetime
            items.append(metric('resolver_last_request_timestamp_seconds', datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()))
    return items


def run_classification_metrics(source, report):
    """Expose only a fixed vocabulary from the latest completed source receipt."""
    outcome = str(report.get('run_outcome') or report.get('run_status') or '').lower()
    statuses = report.get('company_statuses') or {}
    if not outcome and any(isinstance(statuses.get(key), int) and statuses[key] > 0 for key in ('partial', 'source_failed', 'discovery_failed')):
        outcome = 'partial'
    outcome = outcome if outcome in {'complete', 'completed', 'success', 'partial', 'failed'} else 'other'
    items = [metric('source_run_outcome', 1, source=source, outcome=outcome)]
    allowed = {'budget_exhausted', 'partial_suspicious_empty', 'partial_page_anomaly',
               'complete', 'completed', 'failed', 'no_jobs', 'success'}
    for status, count in (report.get('scan_status_counts') or {}).items():
        key = str(status).lower()
        if key in allowed and isinstance(count, (int, float)) and not isinstance(count, bool):
            items.append(metric('source_scan_status', count, source=source, status=key))
    for status, count in statuses.items():
        key = str(status).lower()
        if key in {'partial', 'source_failed', 'discovery_failed', 'completed', 'no_jobs', 'failed'} and isinstance(count, (int, float)) and not isinstance(count, bool):
            items.append(metric('source_scan_status', count, source=source, status=key))
    return items


def company_status_counts(statuses):
    result = {}
    for status, measure in (('partial', 'companies_partial'),
                            ('completed', 'companies_completed'),
                            ('failed', 'companies_failed')):
        count = statuses.get(status)
        if isinstance(count, (int, float)) and not isinstance(count, bool):
            result[measure] = count
    return result


def summary_aliases(source):
    aliases = {'requests': ('requests', 'requests_used', 'requests_made'),
               'selected': ('companies_selected', 'selected_companies'),
               'processed': ('companies_processed', 'companies_selected', 'selected_companies'),
               'completed': ('companies_completed',),
               'deferred': ('companies_deferred', 'companies_deferred_budget'),
               'detail_success': ('detail_successes',), 'detail_failed': ('detail_failures',),
               'browser_navigations': ('browser_navigations',),
               'full_scans': ('companies_completed',),
               'partial_scans': ('companies_partial',),
               'failed_scans': ('companies_failed',),
               'valid_cards': ('valid_cards',),
               'suspicious_empty': ('suspicious_empty_companies',)}
    if source == 'linkedin':
        aliases['jobs_written'] = ('jobs_written',)
    return aliases


def receipts():
    import hashlib
    import importlib.util
    spec = importlib.util.spec_from_file_location('runr_health_observer', '/opt/runr-ops/observe.py')
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    items = []
    allowed = {'companies_selected', 'selected_companies', 'companies_input', 'companies_processed', 'companies_completed',
               'companies_failed', 'companies_deferred', 'companies_deferred_budget', 'companies_partial', 'companies_zero_confirmed',
               'suspicious_empty_companies', 'valid_cards', 'requests', 'requests_used', 'requests_made', 'detail_successes',
               'detail_failures', 'pending_detail_retries', 'blocked_responses', 'browser_navigations', 'fallback_attempts',
               'jobs_written', 'exported_jobs', 'persisted_jobs'}
    for source in ('linkedin', 'employer'):
        receipt = json.loads(Path(f'/srv/runr/exports/receipts/{source}-latest.json').read_text())
        path = Path(f'/srv/runr/exports/receipts/{source}-latest-metrics.json')
        with path.open('rb') as stream:
            matches = hashlib.file_digest(stream, 'sha256').hexdigest() == receipt.get('metrics_sha256')
        items.append(metric('receipt_metrics_match', int(matches), source=source))
        if not matches:
            continue  # Never attribute an in-flight metrics file to an older receipt.
        counts = {}
        def visit(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in allowed and not (source == 'employer' and key in {'jobs_written', 'persisted_jobs', 'exported_jobs'}) and isinstance(value, (int, float)) and not isinstance(value, bool):
                        counts[key] = value
                    elif key == 'company_statuses' and source == 'employer' and isinstance(value, dict):
                        counts.update(company_status_counts(value))
                    elif isinstance(value, dict):
                        visit(value)
        classification = []
        for obj in observer.json_objects(path):
            visit(obj)
            if isinstance(obj, dict) and ('run_outcome' in obj or 'run_status' in obj or 'scan_status_counts' in obj or 'company_statuses' in obj):
                classification = run_classification_metrics(source, obj)
        items += [metric('source_latest', value, source=source, measure=key) for key, value in counts.items()]
        items += classification
        for measure, keys in summary_aliases(source).items():
            value = next((counts[key] for key in keys if key in counts), None)
            if value is not None:
                items.append(metric('source_latest_summary', value, source=source, measure=measure))
    return items


def surfaces():
    items = []
    for surface, url in (('api_public_health', 'https://runr-api.onrender.com/health/live'),
                         ('frontend_public_page', 'https://runr-frontend.onrender.com/')):
        started = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                ok = 200 <= response.status < 300
        except Exception:
            ok = False
        items += [metric('public_surface_up', int(ok), surface=surface),
                  metric('public_surface_latency_seconds', time.monotonic() - started, surface=surface)]
    return items


def stage_charts():
    import importlib.util
    spec = importlib.util.spec_from_file_location('runr_stage_charts', '/opt/runr-ops/stage_charts.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.collect()


def main():
    load_env()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cache = OUTPUT / 'pipeline.json'
    try:
        old = json.loads(cache.read_text()).get('sections', {})
    except (OSError, ValueError):
        old = {}
    sections = {}
    for section, collect in (('configuration', configuration), ('catalog', catalog), ('stage_charts', stage_charts), ('source_stores', source_stores),
                             ('receipts', receipts), ('public_surfaces', surfaces)):
        started = time.monotonic()
        print(json.dumps({'event': 'pipeline_section_start', 'section': section}), flush=True)
        try:
            sections[section] = {'up': True, 'timestamp': time.time(), 'metrics': collect()}
        except Exception as error:
            sections[section] = {**old.get(section, {}), 'up': False, 'error_class': type(error).__name__}
        sections[section]['duration'] = time.monotonic() - started
        print(json.dumps({'event': 'pipeline_section_complete', 'section': section, 'up': sections[section]['up'],
                          'duration_seconds': round(sections[section]['duration'], 3)}), flush=True)
    attempted = time.time()
    for name, text in (('pipeline.json', json.dumps({'attempted_at': attempted, 'sections': sections}, indent=2)),
                       ('pipeline.prom', render(sections, attempted))):
        temporary = OUTPUT / (name + '.tmp')
        temporary.write_text(text + '\n', encoding='utf-8')
        temporary.chmod(0o644)
        temporary.replace(OUTPUT / name)
    print(json.dumps({'sections': {key: {'up': data['up'], 'duration_seconds': round(data['duration'], 3),
        'metrics': len(data.get('metrics', [])), 'error_class': data.get('error_class')} for key, data in sections.items()}}))


if __name__ == '__main__':
    main()
