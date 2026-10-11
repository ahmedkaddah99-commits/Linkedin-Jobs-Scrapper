"""Configure only Runr VPS rules and their owner-selected email contact point."""
import argparse
import json
import runpy
import time
import urllib.error
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
helpers = runpy.run_path(str(ROOT / 'configure-grafana.py'))
request = helpers['request']
GRAFANA = helpers['GRAFANA']
FOLDER = 'runr-vps-ops'
CONTACT_UID = 'runr-vps-owner-email'
CONTACT_NAME = 'Runr VPS owner alerts'
HEAD = 'https://prometheus-prod-65-prod-eu-west-2.grafana.net/api/prom/api/v1/query'
RULES = [
    ('observer', 'VPS monitoring missing or stale',
     '(time() - runr_observer_timestamp_seconds > bool 300) or absent(runr_observer_timestamp_seconds)', '5m', 'critical',
     'The VPS observer has not reported for five minutes. Check host reachability, Alloy and the health timer.'),
    ('timer', 'VPS acquisition timer disabled',
     'max(1 - runr_acquisition_timer_enabled) unless on() (max(runr_acquisition_owner_paused) == 1)', '2m', 'critical',
     'A dedicated acquisition timer is disabled despite the owner running policy. Inspect guard repair logs.'),
    ('receipt', 'VPS acquisition run missing or stale',
     'max((runr_acquisition_last_run_age_seconds > bool 108000) or (1 - runr_acquisition_receipt_present)) unless on() (max(runr_acquisition_owner_paused) == 1)', '5m', 'critical',
     'A collector or publisher has no receipt or has not finished for more than 30 hours.'),
    ('failed', 'VPS acquisition run failed', 'max(runr_acquisition_last_run_failed)', '2m', 'critical',
     'A scraper or publisher failed. Read its receipt, health reasons and journal.'),
    ('partial', 'VPS acquisition outcome partial', 'max(runr_acquisition_last_run_partial)', '10m', 'warning',
     'The latest collection or publication was partial. A zero process exit code does not establish complete coverage.'),
    ('catalog', 'VPS shared catalog inaccessible', '1 - runr_catalog_access_ok', '5m', 'critical',
     'The observer cannot read the intended shared Turso catalog. Check credentials and database connectivity.'),
    ('publication', 'VPS publication head stale', 'time() - runr_catalog_head_timestamp_seconds > bool 108000', '10m', 'critical',
     'The shared publication head has not advanced for 30 hours. Inspect publisher phase and checkpoints.'),
    ('runtime', 'VPS publisher running unusually long', 'max(runr_acquisition_running_elapsed_seconds{source="publisher"}) > bool 7200', '5m', 'warning',
     'Publication has run for more than two hours. Inspect its phase; this alert does not stop the process.'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True)
    parser.add_argument('--send-test', action='store_true')
    args = parser.parse_args()
    editor = Path('user_config/grafana-dashboard-editor-token.txt').read_text().strip()
    reader = Path('user_config/grafana-cloud-observer-read-token.txt').read_text().strip()
    def api(route, *, payload=None, method=None):
        # Resource permissions can take a moment to propagate after creation.
        for attempt in range(5):
            try:
                return request(GRAFANA + route, editor, payload=payload, method=method,
                               headers={'X-Disable-Provenance': 'true'})
            except urllib.error.HTTPError as error:
                if error.code != 403 or attempt == 4:
                    print(json.dumps({'failed_api_route': route, 'http_status': error.code}))
                    raise
                time.sleep(1)
    datasources = api('/api/datasources')
    candidates = [item for item in datasources if item.get('type') == 'prometheus' and item.get('name', '').endswith('-prom')]
    if len(candidates) != 1:
        raise SystemExit('Prometheus datasource selection is ambiguous')
    datasource = candidates[0]['uid']
    for uid, _, query, _, _, _ in RULES:
        result = request(HEAD + '?' + urllib.parse.urlencode({'query': query}), reader, username='3614732')
        if result.get('status') != 'success':
            raise SystemExit('PromQL validation failed for ' + uid)
        print(json.dumps({'validated_rule': uid, 'series': len(result.get('data', {}).get('result', []))}))
    if not any(folder.get('uid') == FOLDER for folder in api('/api/folders')):
        api('/api/folders', payload={'uid': FOLDER, 'title': 'Runr VPS operations'})
    contact = {'uid': CONTACT_UID, 'name': CONTACT_NAME, 'type': 'email',
               'disableResolveMessage': False, 'settings': {'addresses': args.email, 'singleEmail': False}}
    existing_contacts = api('/api/v1/provisioning/contact-points')
    if any(item.get('uid') == CONTACT_UID for item in existing_contacts):
        api('/api/v1/provisioning/contact-points/' + CONTACT_UID, payload=contact, method='PUT')
    else:
        api('/api/v1/provisioning/contact-points', payload=contact)
    existing_rules = {item['uid'] for item in api('/api/v1/provisioning/alert-rules')}
    for suffix, title, query, duration, severity, description in RULES:
        uid = 'runr-vps-' + suffix
        rule = {
            'uid': uid, 'title': title, 'folderUID': FOLDER, 'ruleGroup': 'Runr VPS health',
            'orgId': 1, 'condition': 'B', 'for': duration, 'noDataState': 'Alerting',
            'execErrState': 'Alerting', 'isPaused': False,
            'labels': {'runr_scope': 'vps_acquisition', 'severity': severity},
            'annotations': {'summary': title, 'description': description,
                            '__dashboardUid__': 'runr-vps-acquisition', '__panelId__': '13'},
            'notification_settings': {'receiver': CONTACT_NAME, 'group_by': ['runr_scope'],
                                      'group_wait': '1m', 'group_interval': '10m', 'repeat_interval': '12h'},
            'data': [
                {'refId': 'A', 'queryType': '', 'relativeTimeRange': {'from': 600, 'to': 0},
                 'datasourceUid': datasource, 'model': {'expr': query, 'refId': 'A',
                 'instant': True, 'range': False, 'intervalMs': 1000, 'maxDataPoints': 43200}},
                {'refId': 'B', 'queryType': '', 'relativeTimeRange': {'from': 0, 'to': 0},
                 'datasourceUid': '__expr__', 'model': {'refId': 'B', 'type': 'classic_conditions',
                  'datasource': {'type': '__expr__', 'uid': '__expr__'}, 'conditions': [
                  {'evaluator': {'type': 'gt', 'params': [0.5]}, 'operator': {'type': 'and'},
                   'query': {'params': ['A']}, 'reducer': {'type': 'last', 'params': []}, 'type': 'query'}]}},
            ],
        }
        route = '/api/v1/provisioning/alert-rules' + ('/' + uid if uid in existing_rules else '')
        saved = api(route, payload=rule, method='PUT' if uid in existing_rules else 'POST')
        print(json.dumps({'configured_rule': saved['uid'], 'paused': saved.get('isPaused')}))
    stored = api('/api/v1/provisioning/alert-rules')
    ours = [r for r in stored if r.get('uid', '').startswith('runr-vps-')]
    if len(ours) != len(RULES) or any(r.get('isPaused') or r.get('notification_settings', {}).get('receiver') != CONTACT_NAME for r in ours):
        raise SystemExit('Stored rule verification did not match the intended configuration')
    print(json.dumps({'verified_active_rules': len(ours), 'contact_point': CONTACT_NAME}))
    if args.send_test:
        base = '/apis/notifications.alerting.grafana.app/v1beta1/namespaces/stacks-1845254/receivers'
        receivers = api(base)
        receiver = next(item for item in receivers['items'] if item['spec']['title'] == CONTACT_NAME)
        response = api(base + '/' + receiver['metadata']['name'] + '/test', payload={
            'integration': receiver['spec']['integrations'][0],
            'alert': {'labels': {'alertname': 'RunrVPSNotificationTest', 'runr_scope': 'vps_acquisition'},
                      'annotations': {'summary': 'Runr VPS observability email delivery verification'}}})
        print(json.dumps({'notification_test': response}))


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Grafana API returned HTTP {error.code}; credential and body withheld')
