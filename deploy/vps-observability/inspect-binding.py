"""Print only safe configuration names and database binding metadata."""
import json
from pathlib import Path
from dotenv import dotenv_values
for path in (Path('/opt/runr/.env.acquisition'), Path('/opt/runr/.env')):
    env = dotenv_values(path)
    print(json.dumps({'file': str(path), 'database_backend': env.get('DATABASE_BACKEND'),
        'runtime': env.get('RUNR_ENV'), 'data_dir': env.get('RUNR_DATA_DIR'),
        'turso_url_present': bool(env.get('TURSO_DATABASE_URL')),
        'turso_token_present': bool(env.get('TURSO_AUTH_TOKEN')),
        'live_network': env.get('RUNR_ACQUISITION_LIVE_NETWORK_ENABLED')}))
