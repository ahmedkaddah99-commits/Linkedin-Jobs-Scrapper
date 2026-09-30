import importlib.util
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pipeline = load('pipeline_observer', 'deploy/vps-observability/pipeline.py')
dashboard = load('pipeline_dashboard', 'deploy/vps-observability/configure-pipeline.py')


def company(cid, complete=True):
    row = {'company_id': cid, 'canonical_name': 'PRIVATE COMPANY', 'logo_object_key': '',
           'logo_source_url': 'PRIVATE LOGO URL', 'logo_verified_at': ''}
    for field in pipeline.FIELDS:
        row['fields_' + field] = 'populated' if complete else ''
    row['fields_logo'] = ''  # A source logo still satisfies presence.
    return row


def value(metrics, name, **labels):
    return next(item['value'] for item in metrics if item['name'] == 'runr_pipeline_' + name and item['labels'] == labels)


def test_cohorts_reconcile_and_never_export_rows():
    metrics = pipeline.company_summary([company('private-id-1'), company('private-id-2', False)],
        {'private-id-1'}, {'linkedin': {'private-id-2'}, 'employer': {'private-id-1'}})
    assert value(metrics, 'companies', cohort='all') == 2
    assert value(metrics, 'companies', cohort='core_populated') == 1
    assert value(metrics, 'companies', cohort='core_linkedin_id_not_in_manifest') == 1
    assert value(metrics, 'company_source_cohort', source='linkedin', readiness='core_populated', eligibility='not_in_manifest') == 1
    serialized = json.dumps(metrics)
    assert 'private-id' not in serialized and 'PRIVATE' not in serialized


def test_sentinels_are_not_complete_and_logo_sources_not_double_counted():
    row = company('one')
    row['fields_linkedin_company_id'] = '//'
    row['additional_fields_linkedin_company_id'] = '12345'
    row['fields_logo'] = 'logo'
    row['logo_object_key'] = 'object'
    metrics = pipeline.company_summary([row], set(), {'linkedin': set(), 'employer': set()})
    assert value(metrics, 'company_field_populated', field='logo') == 1
    assert value(metrics, 'company_field_populated', field='linkedin_company_id') == 1
    assert not pipeline.present('//')


def test_failed_section_preserves_old_timestamp_and_does_not_emit_false_zero(tmp_path, monkeypatch):
    old = {'up': True, 'timestamp': 123, 'metrics': [pipeline.metric('companies', 42, cohort='all')]}
    (tmp_path / 'pipeline.json').write_text(json.dumps({'sections': {'catalog': old}}))
    monkeypatch.setattr(pipeline, 'OUTPUT', tmp_path)
    monkeypatch.setattr(pipeline, 'load_env', lambda: None)
    for name in ('configuration', 'source_stores', 'receipts', 'surfaces'):
        monkeypatch.setattr(pipeline, name, lambda: [])
    def fail():
        raise RuntimeError('SECRET credential')
    monkeypatch.setattr(pipeline, 'catalog', fail)
    pipeline.main()
    stored = json.loads((tmp_path / 'pipeline.json').read_text())
    assert stored['sections']['catalog']['timestamp'] == 123
    assert stored['sections']['catalog']['up'] is False
    text = (tmp_path / 'pipeline.prom').read_text()
    assert 'runr_pipeline_companies{cohort="all"} 42' in text
    assert 'runr_pipeline_section_up{section="catalog"} 0' in text
    assert 'SECRET' not in json.dumps(stored)


def test_reason_cardinality_bounded_and_nonfinite_values_omitted():
    assert pipeline.reason('private error URL/token') == 'other'
    assert pipeline.reason('BUDGET_EXHAUSTED') == 'budget_exhausted'
    text = pipeline.render({'test': {'up': True, 'timestamp': 1,
        'metrics': [pipeline.metric('bad', float('nan')), pipeline.metric('good', 4)]}}, 2)
    assert 'bad' not in text
    assert 'runr_pipeline_good 4' in text


def test_sql_aggregation_matches_core_presence_and_external_logo():
    conn = sqlite3.connect(':memory:')
    conn.executescript('CREATE TABLE canonical_companies(company_id TEXT,canonical_name TEXT);'
        'CREATE TABLE canonical_company_profiles(company_id TEXT,profile_json TEXT,logo_source_url TEXT,logo_object_key TEXT,logo_verified_at TEXT);'
        'CREATE TABLE canonical_company_urls(company_id TEXT,url_type TEXT);')
    fields = {key: {'value': 'populated'} for key in ('website', 'industry', 'company_size', 'headquarters')}
    fields['linkedin_company_id'] = {'value': '//'}
    conn.execute('INSERT INTO canonical_companies VALUES (?,?)', ('one', 'Example'))
    conn.execute('INSERT INTO canonical_company_profiles VALUES (?,?,?,?,?)', ('one', json.dumps({'fields': fields,
        'additional_fields': {'linkedin_company_id': {'value': '123'}}}), 'https://logo.example', '', ''))
    row = conn.execute(pipeline.company_flags_sql() + 'SELECT core,linkedin_company_id,logo,career_url FROM ready').fetchone()
    assert row == (1, 1, 1, 0)
    conn.close()


def test_dashboard_is_separate_filterable_aggregate_and_honest():
    result = dashboard.build('prom', 'logs')
    assert result['uid'] != 'runr-vps-acquisition'
    assert {item['name'] for item in result['templating']['list']} == {'source', 'readiness', 'eligibility', 'provider', 'host'}
    assert len({item['id'] for item in result['panels']}) == len(result['panels'])
    pivot = next(item for item in result['panels'] if item['title'] == 'Company-source readiness pivot')
    assert pivot['transformations'][0]['id'] == 'groupingToMatrix'
    text = json.dumps(result)
    assert 'HTTP probes only' in text
    assert 'Stored' in text
    assert 'company_id=' not in text and 'job_id=' not in text


def test_manual_refresh_and_separate_live_source_charts():
    result = dashboard.build('prom', 'logs')
    assert result['refresh'] == ''
    titles = {panel['title'] for panel in result['panels']}
    for source in ('LinkedIn', 'Employer'):
        assert source + ' — pipeline stages now' in titles
        assert source + ' — jobs by day and stage' in titles
        assert source + ' — stage inventory over time' in titles
        assert source + ' — latest run outcomes' in titles
        assert source + ' — latest run outcomes over time' in titles
        assert source + ' — time since last completed run' in titles
    assert not any('city' in title.lower() or 'location' in title.lower() for title in titles)
    assert any('runr_pipeline_stage_jobs' in panel['targets'][0]['expr'] for panel in result['panels'] if panel.get('targets'))


def test_stage_and_run_outcomes_have_real_time_axis_for_each_source():
    result = dashboard.build('prom', 'logs')
    for source in ('LinkedIn', 'Employer'):
        for suffix, metric in (('stage inventory over time', 'runr_pipeline_stage_jobs'),
                               ('latest run outcomes over time', 'runr_pipeline_source_latest_summary')):
            chart = next(panel for panel in result['panels'] if panel['title'] == source + ' — ' + suffix)
            assert chart['type'] == 'timeseries'
            assert chart['targets'][0]['range'] is True
            assert chart['targets'][0]['instant'] is False
            assert metric in chart['targets'][0]['expr']
            assert 'day=' not in chart['targets'][0]['expr']


def test_metric_labels_use_utf8_not_json_unicode_escape():
    line = pipeline.render({'chart': {'up': True, 'timestamp': 1,
        'metrics': [pipeline.metric('stage_city_jobs', 1, city='Münster')]}}, 2)
    assert 'Münster' in line
    assert '\\u' not in line


def test_latest_run_classification_is_bounded_and_keeps_partial_separate():
    values = pipeline.run_classification_metrics('linkedin', {
        'run_outcome': 'PARTIAL',
        'scan_status_counts': {'BUDGET_EXHAUSTED': 84, 'PARTIAL_SUSPICIOUS_EMPTY': 115,
                               'unexpected-private-value': 9},
    })
    assert value(values, 'source_run_outcome', source='linkedin', outcome='partial') == 1
    assert value(values, 'source_scan_status', source='linkedin', status='budget_exhausted') == 84
    assert value(values, 'source_scan_status', source='linkedin', status='partial_suspicious_empty') == 115
    assert 'unexpected-private-value' not in json.dumps(values)


def test_employer_partial_status_is_reported_without_cumulative_written_jobs():
    values = pipeline.run_classification_metrics('employer', {'company_statuses': {'partial': 4}})
    assert value(values, 'source_run_outcome', source='employer', outcome='partial') == 1
    assert value(values, 'source_scan_status', source='employer', status='partial') == 4
    assert 'jobs_written' not in pipeline.summary_aliases('employer')
    assert pipeline.company_status_counts({'partial': 4, 'completed': 2}) == {
        'companies_partial': 4, 'companies_completed': 2}


def test_publication_outcomes_are_visible_before_company_diagnostics():
    titles = [panel['title'] for panel in dashboard.build('prom', 'logs')['panels']]
    assert titles.index('Latest publisher cycle — evaluated versus new / published / rejected') < titles.index('Company inventory and readiness baseline')
    assert titles.index('Publisher task outcomes / rejection reasons — latest cycle') < titles.index('Company inventory and readiness baseline')
