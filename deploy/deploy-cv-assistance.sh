#!/usr/bin/env bash
# CV assistance API and frontend release; no worker, schema or acquisition changes.
set -euo pipefail
commit="${1:?full commit required}"
archive="${2:?git archive path required}"
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || exit 1
[[ "$EUID" == 0 ]] || { echo 'Run through sudo' >&2; exit 1; }
python_bin=/opt/runr/.venv/bin/python
[[ "$("$python_bin" --version)" == 'Python 3.12.7' ]] || exit 1
release="/srv/runr/releases/cv-assistance-${commit:0:8}"
evidence="/srv/runr/ops/cv-assistance-${commit:0:8}"
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
ln -s /opt/runr/.venv "$release/.venv"
chmod +x "$release/deploy/start.sh"
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
    RUNR_RELEASE_COMMIT="$commit" RUNR_RELEASE_BRANCH=release/cv-assistance-2026-10-11 \
    npm run build) > "$evidence/frontend-build.log" 2>&1
"$python_bin" - "$release/frontend/dist" "$commit" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1])
assert json.loads((root/'runr-release.json').read_text())['commit']==sys.argv[2]
assets='\n'.join(p.read_text() for p in (root/'assets').glob('*.js'))
assert 'Customize CV' in assets and 'Generate tailored CV' in assets
assert 'e2e-token' not in assets, 'Test authentication must not ship'
PY
# Abort if another operator changed nginx while this build ran.
cmp --silent "$config" "$evidence/nginx-before.conf" || { echo 'Production configuration changed during build; refusing to overwrite' >&2; exit 1; }
"$python_bin" - "$release" "$commit" <<'PY'
import os,pathlib,subprocess,sys
pid=subprocess.check_output(['systemctl','show','runr-api-candidate','-p','MainPID','--value'],text=True).strip()
os.environ.update(dict(s.split('=',1) for s in pathlib.Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in s))
os.environ['RUNR_RELEASE_COMMIT']=sys.argv[2]
os.environ.pop('RUNR_MIGRATION_HEAD',None)
sys.path.insert(0,sys.argv[1])
from backend.config.env_schema import validate_environment
from backend.api.routes import build_route_registry
validate_environment()
build_route_registry()
print('Production environment and route imports preflight passed')
PY
dropin=/etc/systemd/system/runr-api-candidate.service.d/zz-cv-assistance.conf
if [[ -e "$dropin" ]]; then cp "$dropin" "$evidence/api-before.conf"; fi
restore() {
    cp "$evidence/nginx-before.conf" "$config"
    if [[ -e "$evidence/api-before.conf" ]]; then cp "$evidence/api-before.conf" "$dropin"; else rm -f "$dropin"; fi
    systemctl daemon-reload
    systemctl restart runr-api-candidate
    nginx -t && systemctl reload nginx
}
trap restore ERR
mkdir -p "$(dirname "$dropin")"
cat > "$dropin" <<EOF
[Service]
WorkingDirectory=$release
ExecStart=
ExecStart=$release/deploy/start.sh api
UnsetEnvironment=RUNR_MIGRATION_HEAD
Environment=RUNR_RELEASE_COMMIT=$commit
Environment=RUNR_RELEASE_BRANCH=release/cv-assistance-2026-10-11
EnvironmentFile=/etc/runr/cv-assistance-preview.env
EOF
# Deployment-approved single-job preview; does not alter the user's billing plan.
printf 'CV_CUSTOMIZATION_PREVIEW_USER_ID=%s\nCV_CUSTOMIZATION_PREVIEW_JOB_ID=%s\n' "${3:?preview user required}" "${4:?preview job required}" > /etc/runr/cv-assistance-preview.env
printf 'RUNR_RELEASE_COMMIT=%s\nRUNR_RELEASE_BRANCH=release/cv-assistance-2026-10-11\n' "$commit" >> /etc/runr/cv-assistance-preview.env
chmod 600 /etc/runr/cv-assistance-preview.env
systemctl daemon-reload
systemctl restart runr-api-candidate
ready=false
for attempt in {1..30}; do
    if curl --fail --silent http://127.0.0.1:18000/health/ready > "$evidence/api-ready.json"; then ready=true; break; fi
    sleep 2
done
[[ "$ready" == true ]]
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
