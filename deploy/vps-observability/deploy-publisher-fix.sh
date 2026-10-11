#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
python=/opt/runr/.venv/bin/python
test "$("$python" --version)" = "Python 3.12.7"
backup="/opt/runr-ops/backups/publisher-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0755 "$backup" /etc/systemd/system/runr-acquisition-publisher.service.d
cp -p /opt/runr/scripts/publish_producer_states.py "$backup/publish_producer_states.py"
cp -p /opt/runr/backend/repositories/sqlite_acquisition.py "$backup/sqlite_acquisition.py"
install -m 0644 "$root/publish_producer_states.py" /opt/runr/scripts/publish_producer_states.py
install -m 0644 "$root/sqlite_acquisition.py" /opt/runr/backend/repositories/sqlite_acquisition.py
install -m 0644 "$root/observe.py" /opt/runr-ops/observe.py
install -m 0644 "$root/catalog.py" /opt/runr-ops/catalog.py
install -m 0644 "$root/runr-publisher-progress.conf" /etc/systemd/system/runr-acquisition-publisher.service.d/60-progress.conf
"$python" -m py_compile /opt/runr/scripts/publish_producer_states.py /opt/runr/backend/repositories/sqlite_acquisition.py /opt/runr-ops/observe.py /opt/runr-ops/catalog.py
systemctl daemon-reload
systemctl restart --no-block runr-acquisition-publisher.service
printf 'Publisher recovery restart requested; previous code saved in %s\n' "$backup"
