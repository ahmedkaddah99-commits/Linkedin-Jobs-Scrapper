import json
import sqlite3

from backend.domain.job_filter_source_cache import SOURCE_SCHEMA
from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore


def matches(filters, intelligence, source):
    predicates, parameters = SqlitePersonalizedJobsStore._feed_filter_sql(filters)
    with sqlite3.connect(':memory:') as connection:
        connection.execute('CREATE TABLE catalog(filter_json TEXT,version_payload_json TEXT)')
        connection.execute('INSERT INTO catalog VALUES (?,?)', (json.dumps(intelligence), source))
        return connection.execute('SELECT COUNT(*) FROM catalog WHERE ' + ' AND '.join(predicates), parameters).fetchone()[0]


def test_cached_source_precedence_and_unknown_do_not_read_original_payload():
    intelligence = {'source_metadata_schema': SOURCE_SCHEMA,
                    'source_metadata': {'$.work_arrangement': 'remote'}, 'work_arrangement': 'onsite'}
    assert matches({'work_arrangement': ['remote']}, intelligence, 'must not parse this') == 1
    assert matches({'work_arrangement': ['onsite']}, intelligence, 'must not parse this') == 0
    intelligence['source_metadata'] = {}
    assert matches({'work_arrangement': ['onsite']}, intelligence, 'must not parse this') == 1


def test_numeric_source_cache_preserves_source_years_and_rejects_text():
    intelligence = {'source_metadata_schema': SOURCE_SCHEMA,
                    'source_metadata': {'$.experience_years_min': 2}, 'required_experience_years': 6}
    filters = {'required_experience_min': 2, 'required_experience_max': 2}
    assert matches(filters, intelligence, 'must not parse this') == 1
    intelligence['source_metadata']['$.experience_years_min'] = '2'
    assert matches(filters, intelligence, 'must not parse this') == 0


def test_uncached_or_outdated_cache_uses_original_source():
    intelligence = {'source_metadata_schema': 'outdated',
                    'source_metadata': {'$.work_arrangement': 'remote'}, 'work_arrangement': 'remote'}
    source = json.dumps({'work_arrangement': 'onsite'})
    assert matches({'work_arrangement': ['remote']}, intelligence, source) == 0
    assert matches({'work_arrangement': ['onsite']}, intelligence, source) == 1
    intelligence.pop('source_metadata_schema')
    assert matches({'work_arrangement': ['onsite']}, intelligence, source) == 1
