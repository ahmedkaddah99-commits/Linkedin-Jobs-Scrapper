"""Supply only the intended catalog binding from the authoritative local .env.

Credentials travel on SSH stdin, never in command arguments or displayed output.
Default is a read-only connection/schema probe; --apply installs the publisher overlay.
"""
import argparse
import json
import subprocess
from pathlib import Path
from dotenv import dotenv_values

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--env', type=Path, default=Path('user_config/.env'))
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
env = dotenv_values(args.env)
values = {key: str(env.get(key) or '') for key in ('DATABASE_BACKEND', 'RUNR_ENV', 'TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN')}
if values['DATABASE_BACKEND'] != 'turso' or not values['TURSO_DATABASE_URL'] or not values['TURSO_AUTH_TOKEN']:
    raise SystemExit('Authoritative application configuration lacks Turso binding')
command = ['ssh', 'runr-vps', 'sudo', '/opt/runr/.venv/bin/python', '/tmp/runr-observability-20260926/set-binding.py']
if args.apply:
    command.append('--apply')
result = subprocess.run(command, input=json.dumps(values), text=True, capture_output=True, timeout=60)
print(result.stdout.strip())
if result.returncode:
    # Remote tracebacks can include environment internals; do not print stderr.
    raise SystemExit('Publisher binding operation failed; no success claimed')
