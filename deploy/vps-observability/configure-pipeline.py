"""Build/publish the owner-approved aggregate pipeline dashboard and verify queries."""
import argparse
import json
import runpy
import urllib.parse
import urllib.error
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HELPERS = runpy.run_path(str(ROOT / 'configure-grafana.py'))
request = HELPERS['request']
UID = 'runr-data-pipeline'


def build(prom_uid='grafanacloud-prom', logs_uid='grafanacloud-logs'):
    panels = []
    y = 0
    def text(title, content, height=5):
        nonlocal y
        panels.append({'id': len(panels) + 1, 'type': 'text', 'title': title,
            'gridPos': {'x': 0, 'y': y, 'w': 24, 'h': height},
            'options': {'mode': 'markdown', 'content': content}})
        y += height
    def panel(title, expr, legend='', description='', kind='table', unit='short', height=7):
        nonlocal y
        table = kind == 'table'
        target = {'refId': 'A', 'expr': expr, 'legendFormat': legend,
                  'instant': kind != 'timeseries', 'range': kind == 'timeseries',
                  'format': 'table' if table else 'time_series'}
        value = {'id': len(panels) + 1, 'type': kind, 'title': title, 'description': description,
            'gridPos': {'x': 0, 'y': y, 'w': 24, 'h': height},
            'datasource': {'type': 'prometheus', 'uid': prom_uid}, 'targets': [target],
            'fieldConfig': {'defaults': {'unit': unit, 'decimals': 0}, 'overrides': []},
            'options': {'showHeader': True, 'cellHeight': 'sm'}}
        if table:
            value['transformations'] = [{'id': 'organize', 'options': {'excludeByName': {
                'Time': True, '__name__': True, 'instance': True, 'job': True}, 'renameByName': {'Value': 'Count / value'}}}]
        if kind == 'stat':
            value['options'] = {'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
                'textMode': 'value_and_name', 'colorMode': 'none', 'graphMode': 'none'}
        if kind == 'timeseries':
            value['options'] = {'legend': {'displayMode': 'table', 'placement': 'bottom'}, 'tooltip': {'mode': 'multi'}}
        panels.append(value)
        y += height
        return value
    source = 'source=~"${source:regex}"'
    readiness = 'readiness=~"${readiness:regex}"'
    eligibility = 'eligibility=~"${eligibility:regex}"'
    text('Start here — what these numbers mean',
        '**Companies → approved scraper inputs → producer stores → catalog import → publication head → API / frontend.**\n\n'
        'Stored ≠ fresh; active ≠ published; published ≠ verified Apply URL. Counts at different stages are not a subtraction-based loss calculation. '
        'Tables contain aggregates only. Filters apply to matching source/cohort panels; inventory and host health remain global. '
        'Latest-run panels are snapshots, not per-minute throughput. Unknown / absent metrics are not zero.\n\n'
        '[Existing timer / progress / log dashboard](/d/runr-vps-acquisition/runr-vps-and-scraper-outcomes)', 5)
    panel('At a glance — companies / core populated / producer jobs / published',
        'runr_pipeline_companies{cohort=~"all|core_populated"} or runr_pipeline_source_jobs or runr_pipeline_published_jobs{quality="jobs"}',
        '{{cohort}} {{source}} {{quality}}', kind='stat', height=5)
    for chart_source, title_source in (('linkedin', 'LinkedIn'), ('employer', 'Employer')):
        text(title_source + ' jobs — source-specific pipeline',
            'Trace this source from **selected companies → scan outcome → valid cards / written jobs → detailed → imported → published**. '
            'Latest-run counts and cumulative job inventory have different denominators. Missing evidence is absent, not zero.', 3)
        panel(title_source + ' — latest run outcomes',
            'runr_pipeline_source_latest_summary{source="' + chart_source + '",measure=~"selected|full_scans|partial_scans|failed_scans|valid_cards|detail_success|detail_failed|jobs_written"}',
            '{{measure}}', 'Last hash-matched completed receipt only. Full, partial and failed are company scan outcomes; valid cards are not detailed or published jobs.',
            kind='stat', height=6)
        panel(title_source + ' — latest run outcomes over time',
            'runr_pipeline_source_latest_summary{source="' + chart_source + '",measure=~"selected|full_scans|partial_scans|failed_scans|valid_cards|detail_success|detail_failed|jobs_written"}',
            '{{measure}}', 'Each point shows the latest completed run known at that time. Between runs the value repeats; this is not per-interval throughput. History begins when the observer started.',
            kind='timeseries', height=9)
        panel(title_source + ' — time since last completed run',
            'runr_acquisition_last_run_age_seconds{source="' + chart_source + '"}',
            'Age', 'Age of the most recent completed source receipt; a growing value means no newer run has finished.',
            kind='stat', unit='s', height=4)
        panel(title_source + ' — latest run status and scan reasons',
            'runr_pipeline_source_run_outcome{source="' + chart_source + '"} or runr_pipeline_source_scan_status{source="' + chart_source + '"}',
            '{{outcome}} {{status}}', 'Only observed bounded statuses are shown. A missing status means the producer did not provide it, not that it was successful.',
            kind='table', height=6)
        panel(title_source + ' — pipeline stages now',
            'runr_pipeline_stage_jobs{source="' + chart_source + '"}', '{{stage}}',
            'Distinct jobs per stage for this source; one job can appear in multiple stages.', kind='stat', height=5)
        panel(title_source + ' — stage inventory over time',
            'runr_pipeline_stage_jobs{source="' + chart_source + '"}', '{{stage}}',
            'Five-minute aggregate snapshots from Grafana retention. Lines show inventory at each observation, not new jobs per interval. History begins when this tracker was installed.',
            kind='timeseries', height=9)
        dated = panel(title_source + ' — jobs by day and stage',
            'sum by(day,stage) (runr_pipeline_stage_daily_jobs{source="' + chart_source + '"})',
            '{{stage}}', 'Daily first-known evidence, UTC. Older and Unknown are separate buckets. Published membership with no first-publication evidence is Unknown.',
            kind='barchart', height=9)
        dated['transformations'] = [{'id': 'groupingToMatrix', 'options': {
            'columnField': 'stage', 'rowField': 'day', 'valueField': 'Value', 'emptyValue': 'null'}}]
        dated['options'] = {'orientation': 'vertical', 'xField': 'day', 'stacking': 'off',
                            'showValue': 'auto', 'legend': {'displayMode': 'list', 'placement': 'bottom'}}
        panel(title_source + ' — last successful stage update',
            'runr_pipeline_section_timestamp_seconds{section="stage_charts"}', 'Updated at',
            'Observer computes aggregates independently of browser refresh. Check section health before trusting stale values.',
            kind='stat', unit='dateTimeAsIso', height=4)
    panel('Latest publisher cycle — evaluated versus new / published / rejected', 'runr_pipeline_publisher_latest', '{{measure}}',
        'jobs_published is snapshot size; jobs_new is new catalog ingestion. Zero rejected only describes evaluated candidates.')
    panel('Publisher task outcomes / rejection reasons — latest cycle',
        'runr_pipeline_publisher_tasks or runr_pipeline_publisher_rejections', '{{status}} {{reason}}',
        'Detailed reasons not in the bounded vocabulary appear as other. Zero none means the rejection query returned no records.')
    health = panel('Observer section health — 1 OK / 0 failed', 'runr_pipeline_section_up', '{{section}}', kind='stat', height=4)
    health['options']['colorMode'] = 'value'
    health['fieldConfig']['defaults']['thresholds'] = {'mode': 'absolute', 'steps': [{'color': 'red', 'value': None}, {'color': 'green', 'value': 1}]}
    age = panel('Age of each successful aggregate snapshot', 'time() - runr_pipeline_section_timestamp_seconds', '{{section}}',
        'A failed section retains its last successful data. More than 10 minutes indicates stale telemetry, not a healthy unchanged system.', kind='stat', unit='s', height=4)
    age['options']['colorMode'] = 'value'
    age['fieldConfig']['defaults']['thresholds'] = {'mode': 'absolute', 'steps': [{'color': 'green', 'value': None}, {'color': 'orange', 'value': 600}, {'color': 'red', 'value': 900}]}
    text('Where the data lives',
        '| Store | Location / owner |\n|---|---|\n'
        '| Canonical companies, profiles, URL evidence, catalog jobs, publication head | Shared Turso application database; VPS publisher uses its protected catalog binding |\n'
        '| LinkedIn producer jobs and detail attempts | VPS: `/srv/runr/state/active/linkedin/master_linkedin_jobs_state.db` |\n'
        '| Employer producer jobs and company scan state | VPS: `/srv/runr/state/active/employer/master_employer_jobs_state.db` |\n'
        '| LinkedIn-ID resolver results | VPS: `/srv/runr/state/enrichment/linkedin_id_resolution.sqlite3` |\n'
        '| Approved scraper input snapshot | VPS: `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` |\n'
        '| Run receipts / health | VPS: `/srv/runr/exports/receipts/`; `/var/lib/runr/observability/` |\n'
        '| Preserved recovery assets / logo objects | Cloudflare R2; preservation inventory is separate from current live rows |', 7)
    panel('Company inventory and readiness baseline', 'runr_pipeline_companies', '{{cohort}}',
        'Core populated = name, website, industry, company size, headquarters and any logo reference. Presence is not verification.')
    panel('Company-field completeness (%)', '100 * runr_pipeline_company_field_populated / scalar(runr_pipeline_companies{cohort="all"})', '{{field}}',
        'Percent of all canonical companies. Logo combines sources. Verified timestamp is a separate narrower measurement. Company type/type and revenue/range are separate storage aliases, not additive counts.', unit='percent', height=10)
    panel('Company-source readiness pivot',
        'label_join(sum by(source,readiness,eligibility) (runr_pipeline_company_source_cohort{' + source + ',' + readiness + ',' + eligibility + '}), "cohort", " / ", "readiness", "eligibility")',
        '{{source}} {{readiness}} {{eligibility}}',
        'Rows are readiness / manifest membership; columns are LinkedIn and employer. Not-in-manifest does not itself establish the reason for exclusion.')['transformations'] = [
            {'id': 'groupingToMatrix', 'options': {'columnField': 'source', 'rowField': 'cohort', 'valueField': 'Value', 'emptyValue': 'null'}}]
    panel('Approved scraper inputs and blocked manifest entities',
        'runr_pipeline_manifest_companies{' + source + '} or runr_pipeline_manifest_records', '{{source}} {{status}}',
        'Manifest evidence is separate from live enriched profiles. Blocked entity counts are historical snapshot decisions, not current publication rejections.')
    panel('Why manifest rows are excluded — overlapping reasons', 'runr_pipeline_manifest_exclusions', '{{reason}}',
        'Reasons from the approved input snapshot, not a fresh re-evaluation of live profiles. One row can have multiple reasons. These counts must not be added as unique companies.')
    panel('Configured per-run limits', 'runr_pipeline_configured_limit{' + source + '}', '{{source}} {{limit}}',
        'Actual VPS environment values; fallback wrapper defaults only when no override exists. These are not publication-per-day quotas.')
    panel('Latest scraper run — requests / companies / outcomes', 'runr_pipeline_source_latest_summary{' + source + '}', '{{source}} {{measure}}',
        'Current completed receipt only, hash matched. Processed for LinkedIn means selected/attempted, not a fully completed scan. Unsupported metrics remain absent.', height=10)
    panel('Request budget used (%)',
        '100 * sum by(source)(runr_pipeline_source_latest_summary{' + source + ',measure="requests"}) / on(source) sum by(source)(runr_pipeline_configured_limit{limit="requests",' + source + '})',
        '{{source}}', kind='stat', unit='percent', height=4)
    panel('LinkedIn detail outcomes — why work did not complete', 'runr_pipeline_linkedin_detail_attempts', '{{status}} {{reason}}',
        'Latest database run. BUDGET_EXHAUSTED is not an HTTP blocking response. Other reasons are deliberately bucketed; inspect logs for detail.')
    panel('Employer scan state — cumulative, not latest run', 'runr_pipeline_employer_company_state', '{{status}}',
        'Historical no_jobs is not automatically fresh confirmed-empty evidence.')
    panel('Employer stored jobs by provider', 'runr_pipeline_employer_provider_jobs{provider=~"${provider:regex}"}', '{{provider}}',
        'Cumulative stored rows, not fresh collection. A recognized provider hostname does not prove a native connector works.')
    panel('Producer store inventory', 'runr_pipeline_source_jobs{' + source + '}', '{{source}}', kind='stat', height=4)
    panel('Historical import checkpoints and bootstrap status',
        'label_replace(runr_pipeline_import_checkpoint{' + source + '}, "measure", "checkpoint_rowid", "__name__", ".*") or label_replace(runr_pipeline_import_bootstrap_complete{' + source + '}, "measure", "bootstrap_complete_1_0", "__name__", ".*")', '{{source}} {{measure}}',
        'Checkpoint is a source rowid, not a count of published jobs. Bootstrap complete is 1/0.')
    panel('Rows beyond import checkpoint — backlog proxy',
        'clamp_min(runr_pipeline_source_max_rowid{' + source + '} - on(source) runr_pipeline_import_checkpoint{' + source + '}, 0)', '{{source}}',
        'Rowid distance, not exact pending eligible jobs; rowid gaps/deletions can affect it. Does not count unpublished catalog jobs.', kind='stat', height=4)
    panel('Remaining bootstrap batches at current row limit',
        'ceil(clamp_min(runr_pipeline_source_max_rowid{source="linkedin"} - on(source) runr_pipeline_import_checkpoint{source="linkedin"}, 0) / scalar(runr_pipeline_configured_limit{source="publisher",limit="source_rows"}))',
        'LinkedIn batches', 'Batch estimate, not elapsed time. At a daily cadence this demonstrates the delay; eligibility and new arrivals affect the actual drain.', kind='stat', height=4)
    panel('Catalog inventory by lifecycle', 'runr_pipeline_catalog_jobs', '{{lifecycle}}',
        'Active means lifecycle not closed, not newly verified hiring.')
    panel('Currently published and quality coverage', 'runr_pipeline_published_jobs', '{{quality}}',
        'All quality rows overlap; do not sum. Verified destination is stored status, not authenticated UI proof that Apply succeeds.')
    panel('Active catalog jobs outside current publication', 'runr_pipeline_active_outside_head', 'Not currently served',
        'Not automatically a rejection. Older jobs can be outside the current candidate set.', kind='stat', height=4)
    panel('Data movement over time — store/catalog/publication sizes',
        'runr_pipeline_source_jobs{' + source + '} or sum(runr_pipeline_catalog_jobs) or runr_pipeline_published_jobs{quality="jobs"}',
        '{{__name__}} {{source}}', 'Inventory history begins when this observer was installed. Changes are net inventory changes, not necessarily unique new jobs.', kind='timeseries', height=9)
    panel('LinkedIn-ID resolver inventory', 'runr_pipeline_resolver_records', '{{status}}',
        'URL-resolution rows, not distinct canonical companies.')
    panel('Time since last recorded resolver request', 'time() - runr_pipeline_resolver_last_request_timestamp_seconds',
        'Resolver inactivity', kind='stat', unit='s', height=4)
    panel('Timer/running state and latest run freshness',
        'label_replace(runr_acquisition_timer_enabled{' + source + '}, "measure", "timer_enabled_1_0", "__name__", ".*") or label_replace(runr_acquisition_running{' + source + '}, "measure", "running_1_0", "__name__", ".*") or label_replace(runr_acquisition_last_run_age_seconds{' + source + '}, "measure", "last_run_age_seconds", "__name__", ".*")',
        '{{__name__}} {{source}}', 'Enabled 1/0; running 1/0; age seconds. A oneshot service idle between scheduled runs is normal.')
    panel('Public API / frontend availability', 'runr_pipeline_public_surface_up', '{{surface}}',
        'HTTP probes only. Does NOT verify authenticated jobs, matching, logos or Apply behavior.', kind='stat', height=4)
    panel('VPS CPU busy (%)', '100 * (1 - avg by(instance)(rate(node_cpu_seconds_total{mode="idle",instance=~"${host:regex}"}[5m])))', '{{instance}}',
        'Compare saturation with budget use and error outcomes.', kind='timeseries', unit='percent', height=7)
    panel('VPS available memory', 'node_memory_MemAvailable_bytes{instance=~"${host:regex}"}', '{{instance}}', kind='timeseries', unit='bytes')
    panel('VPS root filesystem free space', 'node_filesystem_avail_bytes{mountpoint="/",fstype!="rootfs",instance=~"${host:regex}"}', '{{instance}}', kind='stat', unit='bytes', height=4)
    panel('Scraper service run peak memory over time', 'runr_acquisition_service_memory_peak_bytes{' + source + '}', '{{source}}',
        'Each sample is the systemd MemoryPeak value for the service at observation time. The line changes when the recorded run peak changes; gaps mean no sample. This is not an all-time maximum. History is limited to retained Grafana samples.',
        kind='timeseries', unit='bytes', height=8)
    panel('Aggregate collector duration / overhead', 'runr_pipeline_section_duration_seconds', '{{section}}', kind='stat', unit='s', height=4)
    text('How to interpret problems — and remaining visibility gaps',
        '- Budget fully used + budget-exhausted/deferred work + idle host: configured cap is a likely bottleneck.\n'
        '- Budget available + repeated detail/discovery failures: investigate scraper/provider/proxy logs.\n'
        '- Growing source backlog: importer lag. Active catalog outside head: inspect candidate selection before blaming missing company data.\n'
        '- Public surface down: serving availability problem; public surface up does not prove the signed-in jobs page works.\n\n'
        '**Not yet measured:** authenticated API/UI served-job counts, deployed revision parity, oldest pending eligible-job age, '
        'and verified end-to-end Apply/image delivery. Do not infer these from aggregate inventory. Historical per-run flow before installation cannot be reconstructed from these new gauges alone.', 7)
    panels.append({'id': len(panels) + 1, 'type': 'logs', 'title': 'Sanitized source outcomes — drill down only when needed',
        'gridPos': {'x': 0, 'y': y, 'w': 24, 'h': 9}, 'datasource': {'type': 'loki', 'uid': logs_uid},
        'targets': [{'refId': 'A', 'expr': '{job="runr/acquisition-health"} | json | source=~"${source:regex}"', 'queryType': 'range'}],
        'options': {'showTime': True, 'sortOrder': 'Descending', 'wrapLogMessage': True}})
    def variable(name, options):
        return {'name': name, 'label': name.replace('_', ' ').title(), 'type': 'custom', 'query': ','.join(options),
                'multi': True, 'includeAll': True, 'allValue': '.*', 'current': {'text': 'All', 'value': '$__all'},
                'options': [{'text': value, 'value': value, 'selected': False} for value in options]}
    return {'uid': UID, 'title': 'Runr — Data Pipeline Overview', 'schemaVersion': 39, 'version': 1,
        'refresh': '', 'time': {'from': 'now-7d', 'to': 'now'}, 'timezone': 'browser',
        'tags': ['runr', 'pipeline', 'companies', 'jobs'], 'panels': panels,
        'description': 'Aggregate company readiness, producer inventory, collection budgets, import backlog, publication and host health. No individual job/company records.',
        'templating': {'list': [variable('source', ['linkedin', 'employer', 'publisher']),
            variable('readiness', ['core_populated', 'core_incomplete']), variable('eligibility', ['included', 'not_in_manifest']),
            variable('provider', ['generic_employer_site', 'greenhouse', 'lever', 'workday', 'personio', 'softgarden', 'recruitee', 'smartrecruiters', 'ashby', 'other']),
            {'name': 'host', 'type': 'query', 'label': 'Host', 'datasource': {'type': 'prometheus', 'uid': prom_uid},
             'query': {'query': 'label_values(node_memory_MemAvailable_bytes, instance)', 'refId': 'host'},
             'multi': True, 'includeAll': True, 'allValue': '.*', 'refresh': 1, 'current': {'text': 'All', 'value': '$__all'}}]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    dashboard = build()
    if args.publish:
        editor = Path('user_config/grafana-dashboard-editor-token.txt').read_text().strip()
        datasources = request(HELPERS['GRAFANA'] + '/api/datasources', editor)
        mapping = {}
        for kind, suffix in (('prometheus', '-prom'), ('loki', '-logs')):
            choices = [value for value in datasources if value.get('type') == kind and value.get('name', '').endswith(suffix)]
            if len(choices) != 1:
                raise RuntimeError('Datasource not uniquely identified: ' + kind)
            mapping[kind] = choices[0]['uid']
        dashboard = build(mapping['prometheus'], mapping['loki'])
        result = request(HELPERS['GRAFANA'] + '/api/dashboards/db', editor,
            payload={'dashboard': dashboard, 'overwrite': True, 'message': 'Owner-requested aggregate pipeline overview'})
        print(json.dumps({'write_status': result.get('status'), 'url': HELPERS['GRAFANA'] + result.get('url', '')}))
        for attempt in range(5):
            try:
                saved = request(HELPERS['GRAFANA'] + '/api/dashboards/uid/' + UID, editor)
                break
            except urllib.error.HTTPError as error:
                if error.code != 403 or attempt == 4:
                    raise
                time.sleep(1)
        print(json.dumps({'status': result.get('status'), 'url': HELPERS['GRAFANA'] + result.get('url', ''),
                          'saved_panels': len(saved['dashboard']['panels'])}))
    if args.verify:
        token = Path('user_config/grafana-cloud-observer-read-token.txt').read_text().strip()
        checks = []
        for panel in dashboard['panels']:
            if panel.get('datasource', {}).get('type') != 'prometheus':
                continue
            expr = panel['targets'][0]['expr']
            for name in ('source', 'readiness', 'eligibility', 'provider', 'host'):
                expr = expr.replace('${' + name + ':regex}', '.*')
            result = request('https://prometheus-prod-65-prod-eu-west-2.grafana.net/api/prom/api/v1/query?' + urllib.parse.urlencode({'query': expr}), token, username='3614732')
            checks.append({'panel': panel['title'], 'status': result.get('status'), 'series': len(result.get('data', {}).get('result', []))})
        print(json.dumps({'query_checks': checks}, indent=2))
    if not (args.publish or args.verify):
        print(json.dumps(dashboard, indent=2))


if __name__ == '__main__':
    import urllib.error
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Grafana HTTP {error.code}; credential and response body withheld')
