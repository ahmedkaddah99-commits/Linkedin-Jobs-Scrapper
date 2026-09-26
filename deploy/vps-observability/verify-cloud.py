"""Verify ingestion using the installed credential, printing no credential or log payload."""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

config = Path('/etc/alloy/config.alloy').read_text()
secret_text = Path('/etc/systemd/system/alloy.service.d/env.conf').read_text()
token = re.search(r'GCLOUD_RW_API_KEY=([^"\s]+)', secret_text).group(1)
checks = [
    ('metrics', 'metrics_service', '/api/prom/api/v1/query', {'query': 'runr_acquisition_timer_enabled'}),
    ('logs', 'grafana_cloud_loki', '/loki/api/v1/query_range', {'query': '{job="runr/acquisition-health"}', 'limit': '3'}),
]
for name, component, route, params in checks:
    section = config.split('"' + component + '" {', 1)[1]
    url = re.search(r'url\s*=\s*"([^"]+)"', section).group(1)
    username = re.search(r'username\s*=\s*"([^"]+)"', section).group(1)
    origin = urllib.parse.urlsplit(url)
    target = f'{origin.scheme}://{origin.netloc}{route}?' + urllib.parse.urlencode(params)
    auth = base64.b64encode(f'{username}:{token}'.encode()).decode()
    request = urllib.request.Request(target, headers={'Authorization': 'Basic ' + auth})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
            results = body.get('data', {}).get('result', [])
            print(json.dumps({'check': name, 'http_status': response.status, 'series_or_streams': len(results),
                              'sources': [r.get('metric', {}).get('source') for r in results] if name == 'metrics' else []}))
    except urllib.error.HTTPError as error:
        print(json.dumps({'check': name, 'http_status': error.code, 'read_access': 'denied' if error.code in {401, 403} else 'failed'}))
