"""Bounded, read-only job-stage aggregates for the VPS Grafana observer."""
from __future__ import annotations

import json
import re
import sqlite3
import os
from itertools import chain
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

STAGES = ('collected', 'detailed', 'imported', 'published')
SOURCES = ('linkedin', 'employer')
CITY_ALIASES = {
    'berlin': 'Berlin', 'hamburg': 'Hamburg', 'münchen': 'Munich', 'munich': 'Munich',
    'frankfurt': 'Frankfurt', 'köln': 'Cologne', 'cologne': 'Cologne',
    'stuttgart': 'Stuttgart', 'düsseldorf': 'Düsseldorf', 'dusseldorf': 'Düsseldorf',
    'leipzig': 'Leipzig', 'dortmund': 'Dortmund', 'essen': 'Essen',
    'bremen': 'Bremen', 'dresden': 'Dresden', 'hannover': 'Hanover',
    'hanover': 'Hanover', 'nürnberg': 'Nuremberg', 'nuremberg': 'Nuremberg',
    'bonn': 'Bonn', 'duisburg': 'Duisburg', 'bochum': 'Bochum',
    'wuppertal': 'Wuppertal', 'bielefeld': 'Bielefeld', 'mannheim': 'Mannheim',
    'karlsruhe': 'Karlsruhe', 'augsburg': 'Augsburg', 'wiesbaden': 'Wiesbaden',
    'münster': 'Münster', 'munster': 'Münster', 'aachen': 'Aachen',
}
CITY_PATTERN = re.compile(r'(?<![\w])(' + '|'.join(re.escape(name) for name in CITY_ALIASES) + r')(?![\w])', re.I)


def city(location):
    raw = str(location or '').strip()
    if not raw or re.search(r'\b(remote|homeoffice|home office|anywhere)\b', raw, re.I):
        return 'Unknown'
    names = {CITY_ALIASES[match.group().lower()] for match in CITY_PATTERN.finditer(raw)}
    return next(iter(names)) if len(names) == 1 else 'Unknown'


def day(value, *, as_of=None):
    if not value:
        return 'Unknown'
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        bucket = parsed.date()
        today = date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
        if bucket > today:
            return 'Unknown'
        return 'Older' if bucket < today - timedelta(days=89) else bucket.isoformat()
    except ValueError:
        return 'Unknown'


def aggregate(rows, source, stage, top_cities, *, as_of=None):
    distinct = {}
    for row in rows:
        identity = str(row.get('id') or '')
        if not identity:
            continue
        previous = distinct.get(identity)
        if previous is None or (row.get('date') and (not previous.get('date') or row['date'] < previous['date'])):
            distinct[identity] = row
    result = Counter()
    for row in distinct.values():
        place = city(row.get('location'))
        result[(source, stage, place if place == 'Unknown' or place in top_cities else 'Other', day(row.get('date'), as_of=as_of))] += 1
    return result


def stage_counts(memberships):
    return {stage: len(set(memberships.get(stage, ()))) for stage in STAGES}


def _source_path(env, source):
    key = 'RUNR_LINKEDIN_STATE_DB' if source == 'linkedin' else 'RUNR_EMPLOYER_STATE_DB'
    fallback = f'/srv/runr/state/active/{source}/master_{source}_jobs_state.db'
    return Path(env.get(key, fallback)).resolve(strict=True)


def source_records(env):
    """Yield only stage identity, date and location; never retain job payloads."""
    for source in SOURCES:
        path = _source_path(env, source)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=20)) as conn:
            conn.execute('PRAGMA query_only=ON')
            if source == 'linkedin':
                # Search cards can precede successful detail retrieval.
                for jid, payload, stamp in conn.execute('SELECT s.linkedin_job_id,s.card_json,r.started_at FROM search_cards s LEFT JOIN runs r ON r.run_id=s.run_id'):
                    card = json.loads(payload or '{}')
                    yield source, 'collected', {'id': jid, 'location': card.get('location'), 'date': stamp}
                for jid, payload in conn.execute('SELECT linkedin_job_id,job_json FROM jobs'):
                    job = json.loads(payload or '{}')
                    row = {'id': jid, 'location': job.get('location'), 'date': job.get('first_seen_at')}
                    yield source, 'collected', row
                    yield source, 'detailed', row
            else:
                for jid, payload in conn.execute('SELECT source_key,payload_json FROM jobs'):
                    job = json.loads(payload or '{}')
                    row = {'id': jid, 'location': job.get('location_raw') or job.get('location'), 'date': job.get('first_seen_at')}
                    yield source, 'collected', row
                    if job.get('job_title') and (job.get('description') or job.get('description_text')):
                        yield source, 'detailed', row


def catalog_records(connection):
    """Map canonical jobs to sources using persisted observations only."""
    query = """SELECT o.canonical_job_id,o.source_ats,j.location,
        MIN(o.observed_at) AS first_observed,
        MAX(CASE WHEN h.publication_id IS NOT NULL THEN 1 ELSE 0 END) AS in_head
        FROM job_source_observations o
        JOIN canonical_jobs j ON j.canonical_job_id=o.canonical_job_id
        LEFT JOIN acquisition_publication_jobs p ON p.canonical_job_id=j.canonical_job_id
        LEFT JOIN acquisition_publication_head h ON h.head_id=1 AND h.publication_id=p.publication_id
        GROUP BY o.canonical_job_id,o.source_ats,j.location"""
    cursor = connection.execute(query)
    for canonical_id, provider, location, stamp, published in cursor.fetchall():
        source = 'linkedin' if str(provider).lower() == 'linkedin' else 'employer'
        row = {'id': canonical_id, 'location': location, 'date': stamp}
        yield source, 'imported', row
        if published:
            # Current membership has no reliable first-publication timestamp.
            yield source, 'published', {**row, 'date': ''}


def summarize(records, *, as_of=None):
    """Return bounded stage/city/day aggregates and exact source-stage totals."""
    # Disk-backed aggregation prevents 188k+ producer payloads from competing
    # with the observer's 256 MiB cgroup memory ceiling.
    with TemporaryDirectory(prefix='runr-stage-') as directory:
        with closing(sqlite3.connect(str(Path(directory) / 'stage.sqlite3'))) as conn:
            conn.execute('CREATE TABLE members(source TEXT,stage TEXT,id TEXT,city TEXT,day TEXT,PRIMARY KEY(source,stage,id)) WITHOUT ROWID')
            insert = """INSERT INTO members VALUES (?,?,?,?,?) ON CONFLICT(source,stage,id) DO UPDATE SET
                city=CASE WHEN excluded.day<>'' AND (members.day='' OR excluded.day<members.day) THEN excluded.city ELSE members.city END,
                day=CASE WHEN excluded.day<>'' AND (members.day='' OR excluded.day<members.day) THEN excluded.day ELSE members.day END"""
            batch = []
            for source, stage, row in records:
                if source not in SOURCES or stage not in STAGES or not row.get('id'):
                    continue
                batch.append((source, stage, str(row['id']), city(row.get('location')), str(row.get('date') or '')))
                if len(batch) == 1000:
                    conn.executemany(insert, batch)
                    batch.clear()
            if batch:
                conn.executemany(insert, batch)
            totals = {(source, stage): 0 for source in SOURCES for stage in STAGES}
            for source, stage, count in conn.execute('SELECT source,stage,COUNT(*) FROM members GROUP BY source,stage'):
                totals[(source, stage)] = count
            top = {}
            for source in SOURCES:
                top[source] = {place for place, _ in conn.execute(
                    "SELECT city,COUNT(*) FROM members WHERE source=? AND stage='detailed' AND city<>'Unknown' GROUP BY city ORDER BY COUNT(*) DESC,city LIMIT 10", (source,))}
            grouped = Counter()
            for source, stage, place, stamp, count in conn.execute(
                    'SELECT source,stage,city,day,COUNT(*) FROM members GROUP BY source,stage,city,day'):
                bucket = place if place == 'Unknown' or place in top[source] else 'Other'
                grouped[(source, stage, bucket, day(stamp, as_of=as_of))] += count
            return totals, grouped


def collect(env=None, *, as_of=None):
    """Collect bounded metrics from producer SQLite and shared remote catalog."""
    env = env or os.environ
    if not env.get('TURSO_DATABASE_URL') or not env.get('TURSO_AUTH_TOKEN'):
        raise RuntimeError('shared_catalog_binding_missing')
    import libsql
    conn = libsql.connect(database=env['TURSO_DATABASE_URL'], auth_token=env['TURSO_AUTH_TOKEN'])
    try:
        totals, grouped = summarize(chain(source_records(env), catalog_records(conn)), as_of=as_of)
    finally:
        conn.close()
    from collections import defaultdict
    current_city = Counter()
    daily = Counter()
    for (source, stage, place, bucket), n in grouped.items():
        current_city[(source, stage, place)] += n
        daily[(source, stage, bucket)] += n
    values = []
    for (source, stage), n in totals.items():
        values.append({'name': 'runr_pipeline_stage_jobs', 'value': n, 'labels': {'source': source, 'stage': stage}})
    for (source, stage, place), n in current_city.items():
        values.append({'name': 'runr_pipeline_stage_city_jobs', 'value': n,
                       'labels': {'source': source, 'stage': stage, 'city': place}})
    for (source, stage, bucket), n in daily.items():
        values.append({'name': 'runr_pipeline_stage_daily_jobs', 'value': n,
                       'labels': {'source': source, 'stage': stage, 'day': bucket}})
    return values
