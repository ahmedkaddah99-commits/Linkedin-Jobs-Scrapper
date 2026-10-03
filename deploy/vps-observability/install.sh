#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
python=/opt/runr/.venv/bin/python
test "$("$python" --version)" = "Python 3.12.7"
install -d -m 0755 /opt/runr-ops /etc/runr /var/lib/runr/observability
install -m 0644 "$root/observe.py" /opt/runr-ops/observe.py
install -m 0644 "$root/catalog.py" /opt/runr-ops/catalog.py
install -m 0644 "$root/acquisition-policy.json" /etc/runr/acquisition-policy.json
# Align the documented network switch with the owner's running policy. The
# separate legacy scheduler stays disabled to preserve one source owner.
"$python" - <<'PY'
from pathlib import Path
path = Path('/opt/runr/.env.acquisition')
text = path.read_text()
lines = text.splitlines()
key = 'RUNR_ACQUISITION_LIVE_NETWORK_ENABLED='
lines = [key + 'true' if line.startswith(key) else line for line in lines]
if not any(line.startswith(key) for line in lines):
    lines.append(key + 'true')
path.write_text('\n'.join(lines) + '\n')
PY
install -m 0644 "$root/runr-acquisition-health.service" /etc/systemd/system/runr-acquisition-health.service
install -m 0644 "$root/runr-acquisition-health.timer" /etc/systemd/system/runr-acquisition-health.timer
backup="/etc/alloy/config.alloy.before-runr-health-$(date -u +%Y%m%dT%H%M%SZ)"
cp -p /etc/alloy/config.alloy "$backup"
"$python" - "$root/runr.alloy" <<'PY'
from pathlib import Path
import sys
path = Path('/etc/alloy/config.alloy')
text = path.read_text()
begin = '// BEGIN RUNR ACQUISITION OBSERVABILITY'
end = '// END RUNR ACQUISITION OBSERVABILITY'
if begin in text:
    before, _, rest = text.partition(begin)
    _, found, after = rest.partition(end)
    if not found:
        raise SystemExit('Incomplete Runr block; refusing to modify Alloy')
    text = before + after
path.write_text(text.rstrip() + '\n\n' + Path(sys.argv[1]).read_text())
PY
if ! alloy validate /etc/alloy/config.alloy; then
  cp -p "$backup" /etc/alloy/config.alloy
  exit 1
fi
systemctl daemon-reload
systemctl enable --now runr-acquisition-linkedin.timer runr-acquisition-employer.timer runr-acquisition-publisher.timer runr-acquisition-health.timer
systemctl start runr-acquisition-health.service
if ! systemctl restart alloy; then
  cp -p "$backup" /etc/alloy/config.alloy
  systemctl restart alloy
  exit 1
fi
printf 'Installed Runr health observer. Alloy rollback: %s\n' "$backup"
