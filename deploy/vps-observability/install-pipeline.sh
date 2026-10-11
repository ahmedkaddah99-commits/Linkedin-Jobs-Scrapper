#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
python=/opt/runr/.venv/bin/python
test "$("$python" --version)" = "Python 3.12.7"
"$python" -m pip install --disable-pip-version-check --requirement "$root/pipeline-requirements.txt"
install -d -m 0755 /opt/runr-ops /var/lib/runr/observability
stamp=$(date -u +%Y%m%dT%H%M%SZ)
if test -f /opt/runr-ops/pipeline.py; then
  cp -p /opt/runr-ops/pipeline.py "/opt/runr-ops/pipeline.py.before-$stamp"
fi
install -m 0644 "$root/pipeline.py" /opt/runr-ops/pipeline.py
install -m 0644 "$root/stage_charts.py" /opt/runr-ops/stage_charts.py
install -m 0644 "$root/runr-pipeline-overview.service" /etc/systemd/system/runr-pipeline-overview.service
install -m 0644 "$root/runr-pipeline-overview.timer" /etc/systemd/system/runr-pipeline-overview.timer
systemctl daemon-reload
systemctl enable --now runr-pipeline-overview.timer
systemctl start runr-pipeline-overview.service
systemctl is-enabled runr-pipeline-overview.timer
systemctl is-active runr-pipeline-overview.timer
"$python" - <<'PY'
import json
from pathlib import Path
data=json.loads(Path('/var/lib/runr/observability/pipeline.json').read_text())
summary={key: {'up': value['up'], 'duration_seconds': round(value['duration'],3),
              'metrics': len(value.get('metrics',[])), 'error_class': value.get('error_class')}
         for key,value in data['sections'].items()}
print(json.dumps({'sections':summary}))
if not all(section['up'] for section in data['sections'].values()):
    raise SystemExit('A pipeline section failed; inspect the safe error classes above.')
PY
# Existing Alloy textfile exporter reads every .prom file in this directory.
# Do not restart Alloy or change any collector/publisher/backup settings.
