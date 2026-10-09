"""Read-only Render binding verification; never print environment secrets."""
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'user_config/.env')


def get(path):
    request = Request('https://api.render.com/v1/'+path, headers={'Authorization': 'Bearer '+os.environ['RENDER_API_KEY'].strip()})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


result = []
try:
    for item in get('services?limit=20'):
        service = item.get('service', item)
        if service.get('name') not in ('runr-api', 'runr-worker'):
            continue
        values = {}
        for entry in get('services/'+service['id']+'/env-vars?limit=100'):
            env = entry.get('envVar', entry)
            values[env['key']] = env.get('value', '')
        url = values.get('TURSO_DATABASE_URL', '')
        result.append({'service': service['name'], 'database_backend': values.get('DATABASE_BACKEND'),
            'turso_binding_present': bool(url), 'turso_url_sha256': hashlib.sha256(url.rstrip('/').encode()).hexdigest() if url else None,
            'matches_inspected_turso': bool(url) and url.rstrip('/') == os.environ.get('TURSO_DATABASE_URL', '').rstrip('/')})
except Exception as exc:
    result.append({'status': 'binding_check_unavailable', 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None)})
print(json.dumps(result, indent=2))
