#!/usr/bin/env bash
# Frontend-only immutable release; does not restart customer workers or acquisition.
set -euo pipefail
commit="${1:?full commit required}"
archive="${2:?git archive path required}"
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || exit 1
[[ "$EUID" == 0 ]] || { echo 'Run through sudo' >&2; exit 1; }
python_bin=/opt/runr/.venv/bin/python
[[ "$("$python_bin" --version)" == 'Python 3.12.7' ]] || exit 1
release="/srv/runr/releases/jobs-filter-bar-${commit:0:8}"
evidence="/srv/runr/ops/jobs-filter-bar-${commit:0:8}"
config=/etc/nginx/sites-available/runr-public
mkdir -p /srv/runr/ops
exec 9>/srv/runr/ops/frontend-deployment.lock
flock -n 9 || { echo 'Another frontend release is in progress' >&2; exit 1; }
[[ ! -e "$release" ]] || { echo 'Release already exists' >&2; exit 1; }
current_dist=$(awk '/^[[:space:]]*root / {gsub(/;/,"",$2); print $2; exit}' "$config")
[[ "$current_dist" == /srv/runr/releases/*/frontend/dist ]] || { echo 'Unexpected current frontend root' >&2; exit 1; }
mkdir -p "$release" "$evidence"
cp "$config" "$evidence/nginx-before.conf"
tar -xzf "$archive" -C "$release"
publishable_key=$("$python_bin" - "$current_dist" <<'PY'
import pathlib,re,sys
for path in pathlib.Path(sys.argv[1], 'assets').glob('*.js'):
    match=re.search(r'pk_(?:live|test)_[A-Za-z0-9_=\-]+', path.read_text())
    if match:
        print(match.group()); break
else:
    raise SystemExit('Cannot preserve production Clerk publishable key')
PY
)
chown -R runr:runr "$release"
install -d -o runr -g runr /var/lib/runr/npm-cache
sudo -u runr npm --prefix "$release/frontend" ci --cache /var/lib/runr/npm-cache > "$evidence/npm-ci.log" 2>&1
(cd "$release/frontend" && sudo -u runr env VITE_CLERK_PUBLISHABLE_KEY="$publishable_key" \
    VITE_API_BASE_URL=https://app.userunr.com/v1 VITE_PERSONALIZED_JOBS_EXPERIENCE=1 \
    VITE_PERSONALIZED_JOBS_DATA_MODE=real VITE_REPLACE_LEGACY_JOBS_NAV=1 VITE_E2E_AUTH=0 VITE_E2E_ADMIN=0 \
    RUNR_RELEASE_COMMIT="$commit" RUNR_RELEASE_BRANCH=release/jobs-filter-bar-2026-10-12 \
    npm run build) > "$evidence/frontend-build.log" 2>&1
"$python_bin" - "$release/frontend/dist" "$commit" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1])
assert json.loads((root/'runr-release.json').read_text())['commit']==sys.argv[2]
assets='\n'.join(p.read_text() for p in (root/'assets').glob('*.js'))
css=''.join(p.read_text() for p in (root/'assets').glob('*.css'))
assert 'jobs-filter-pill__label' in css and '#jobs-nav-search' in css
assert 'zoom:.6' not in css and 'zoom:.8' not in css
assert 'data-filter=industry' not in css and 'data-filter=requiredExperience' not in css
assert 'e2e-token' not in assets, 'Test authentication must not ship'
PY
# Abort if another operator changed nginx while this build ran.
cmp --silent "$config" "$evidence/nginx-before.conf" || { echo 'Production configuration changed during build; refusing to overwrite' >&2; exit 1; }
restore() { cp "$evidence/nginx-before.conf" "$config"; nginx -t && systemctl reload nginx; }
trap restore ERR
"$python_bin" - "$config" "$current_dist" "$release/frontend/dist" <<'PY'
import pathlib,sys
path=pathlib.Path(sys.argv[1]); text=path.read_text()
assert sys.argv[2] in text
path.write_text(text.replace(sys.argv[2],sys.argv[3]))
PY
nginx -t
systemctl reload nginx
"$python_bin" - "$evidence/frontend-release.json" "$commit" <<'PY'
import json,pathlib,sys,time,urllib.request
for attempt in range(15):
    try:
        with urllib.request.urlopen('https://app.userunr.com/runr-release.json', timeout=10) as response:
            payload=response.read()
        if json.loads(payload)['commit']==sys.argv[2]:
            pathlib.Path(sys.argv[1]).write_bytes(payload)
            break
    except (OSError, ValueError, KeyError):
        pass
    time.sleep(2)
else:
    raise SystemExit('Public release did not converge after nginx reload')
PY
curl --fail --silent https://app.userunr.com/jobs > "$evidence/jobs.html"
trap - ERR
echo "Frontend release verified: $commit"
