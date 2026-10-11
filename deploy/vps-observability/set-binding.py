"""Receive scoped publisher credentials over stdin, validate, then install if requested."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
values = json.load(sys.stdin)
keys = ('DATABASE_BACKEND', 'RUNR_ENV', 'TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN')
if set(values) != set(keys) or any('\n' in str(v) or '\r' in str(v) for v in values.values()):
    raise SystemExit('Invalid scoped configuration')
os.environ.update(values)
sys.path.insert(0, '/opt/runr')
from backend.database.connection import connect_database
try:
    connection = connect_database('/var/lib/runr/acquisition-data/backend.sqlite3')
    head = connection.execute('SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1').fetchone()
    connection.execute('SELECT source,source_rowid,source_watermark,bootstrap_complete,last_cycle_id,last_publication_id,updated_at FROM acquisition_publisher_checkpoints LIMIT 1').fetchall()
    connection.close()
except Exception as error:
    print(json.dumps({'binding_verified': False, 'error': type(error).__name__}))
    raise SystemExit(1)
if args.apply:
    root = Path('/etc/runr')
    root.mkdir(exist_ok=True)
    path = root / 'acquisition-catalog.env'
    if path.exists():
        raise SystemExit('Publisher overlay already exists; inspect before replacing')
    text = '\n'.join(k + '="' + str(values[k]).replace('\\', '\\\\').replace('"', '\\"') + '"' for k in keys) + '\n'
    # Create privately before writing any credential bytes.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    import grp
    os.chown(path, 0, grp.getgrnam('runr-acquisition').gr_gid)
    dropin = Path('/etc/systemd/system/runr-acquisition-publisher.service.d')
    dropin.mkdir(exist_ok=True)
    (dropin / '50-owner-approved-catalog.conf').write_text('[Service]\nEnvironmentFile=/etc/runr/acquisition-catalog.env\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
print(json.dumps({'binding_verified': True, 'publisher_overlay_installed': args.apply, 'head': dict(head) if head else {}}))
