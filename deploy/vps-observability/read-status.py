"""Agent entry point for bounded Grafana metrics, scraper health and alert states."""
import argparse
import json
import runpy
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path

helpers = runpy.run_path(str(Path(__file__).with_name('configure-grafana.py')))
request = helpers['request']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh', action='store_true', help='Include the current VPS snapshot, without cloud ingestion delay')
    parser.add_argument('--alerts', action='store_true', help='Read Grafana rule evaluation states using the Editor token')
    args = parser.parse_args()
    token = Path('user_config/grafana-cloud-observer-read-token.txt').read_text().strip()
    report = {}
    query = '{__name__=~"runr_(acquisition|catalog|observer).*"}'
    result = request('https://prometheus-prod-65-prod-eu-west-2.grafana.net/api/prom/api/v1/query?' + urllib.parse.urlencode({'query': query}), token, username='3614732')
    report['metrics'] = [{**item['metric'], 'query_time': item['value'][0], 'value': item['value'][1]} for item in result['data']['result']]
    logs = request('https://logs-prod-012.grafana.net/loki/api/v1/query_range?' + urllib.parse.urlencode({'query': '{job="runr/acquisition-health"}', 'limit': 12, 'direction': 'backward'}), token, username='1803034')
    latest = {}
    for stream in logs['data']['result']:
        for timestamp, line in stream['values']:
            event = json.loads(line)
            source = event.get('source')
            if source in {'linkedin', 'employer', 'publisher'} and (source not in latest or int(timestamp) > latest[source][0]):
                latest[source] = (int(timestamp), event)
    report['cloud_health'] = {source: item[1] for source, item in latest.items()}
    if args.ssh:
        result = subprocess.run(['ssh', 'runr-vps', 'cat /var/lib/runr/observability/health.json'], capture_output=True, text=True, timeout=30, check=True)
        report['vps_health'] = json.loads(result.stdout)
    if args.alerts:
        editor = Path('user_config/grafana-dashboard-editor-token.txt').read_text().strip()
        rules = request(helpers['GRAFANA'] + '/api/prometheus/grafana/api/v1/rules', editor)
        report['alerts'] = [{key: rule.get(key) for key in ('name', 'state', 'health', 'lastEvaluation', 'lastError')}
                            for group in rules['data'].get('groups', []) for rule in group.get('rules', [])
                            if rule.get('name', '').startswith('VPS')]
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Grafana read API returned HTTP {error.code}; credential and response body withheld')
