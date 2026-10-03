"""Install the prepared Runr dashboard using a separate Grafana Editor token.

Cloud read verification needs a separate access-policy token with metrics:read
and logs:read; neither credential is printed or sent through shell arguments.
"""
import argparse
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GRAFANA = 'https://pluckyhovercraft81.grafana.net'


def request(url, token, *, payload=None, username=None, method=None, headers=None):
    auth = 'Basic ' + base64.b64encode(f'{username}:{token}'.encode()).decode() if username else 'Bearer ' + token
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={'Authorization': auth, 'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-dashboard', action='store_true')
    parser.add_argument('--verify-cloud', action='store_true')
    args = parser.parse_args()
    if args.verify_cloud:
        token = Path('user_config/grafana-cloud-observer-read-token.txt').read_text().strip()
        for name, origin, user, route, params in (
            ('metrics', 'https://prometheus-prod-65-prod-eu-west-2.grafana.net', '3614732', '/api/prom/api/v1/query', {'query': 'runr_acquisition_timer_enabled'}),
            ('logs', 'https://logs-prod-012.grafana.net', '1803034', '/loki/api/v1/query_range', {'query': '{job="runr/acquisition-health"}', 'limit': '3'}),
        ):
            result = request(origin + route + '?' + urllib.parse.urlencode(params), token, username=user)
            rows = result.get('data', {}).get('result', [])
            print(json.dumps({'check': name, 'status': result.get('status'), 'series_or_streams': len(rows)}))
    if args.publish_dashboard:
        token = Path('user_config/grafana-dashboard-editor-token.txt').read_text().strip()
        datasources = request(GRAFANA + '/api/datasources', token)
        dashboard = json.loads((ROOT / 'dashboard.json').read_text())
        mapping = {}
        for kind, suffix in (('prometheus', '-prom'), ('loki', '-logs')):
            choices = [d for d in datasources if d.get('type') == kind and d.get('name', '').endswith(suffix)]
            if len(choices) != 1:
                raise SystemExit('Cannot uniquely identify the provisioned ' + kind + ' datasource')
            mapping[kind] = choices[0]['uid']
        for panel in dashboard['panels']:
            panel['datasource']['uid'] = mapping[panel['datasource']['type']]
        labels = {
            1: [('Disabled', 'red'), ('Enabled', 'green')],
            2: [('Waiting', 'text'), ('Running', 'blue')],
            4: [('No partial result reported', 'text'), ('Partial', 'orange')],
            5: [('No failure reported', 'green'), ('Failed', 'red')],
            6: [('Unknown', 'orange'), ('Known', 'blue')],
            10: [('Unreachable', 'red'), ('Connected', 'green')],
        }
        for panel in dashboard['panels']:
            if panel['id'] in labels:
                panel['fieldConfig']['defaults']['mappings'] = [{'type': 'value', 'options': {
                    str(index): {'text': text, 'color': color, 'index': index}
                    for index, (text, color) in enumerate(labels[panel['id']])}}]
        result = request(GRAFANA + '/api/dashboards/db', token, payload={'dashboard': dashboard, 'overwrite': True, 'message': 'Owner-approved VPS scraper observability'})
        print(json.dumps({'dashboard_status': result.get('status'), 'url': GRAFANA + result.get('url', '')}))


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Grafana API returned HTTP {error.code}; credential and response body withheld')
