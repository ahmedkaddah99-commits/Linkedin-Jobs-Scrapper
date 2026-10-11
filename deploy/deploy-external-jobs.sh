#!/usr/bin/env bash
# Install an immutable customer release without changing acquisition services.
set -euo pipefail
commit="${1:?full release commit required}"
archive="${2:?git archive path required}"
resume="${3:-}"
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid release commit' >&2; exit 1; }
[[ "$EUID" == 0 ]] || { echo 'Run through sudo' >&2; exit 1; }
short="${commit:0:8}"
release="/srv/runr/releases/external-jobs-$short"
evidence="/srv/runr/ops/external-jobs-$short"
python_bin=/opt/runr/.venv/bin/python
[[ "$($python_bin --version)" == 'Python 3.12.7' ]] || exit 1
current_dist=$(awk '/^[[:space:]]*root / {gsub(/;/,"",$2); print $2; exit}' /etc/nginx/sites-available/runr-public)
[[ "$current_dist" != "$release/frontend/dist" ]] || { echo 'Release is already serving production' >&2; exit 1; }
if [[ "$resume" == --resume ]]; then
    "$python_bin" - "$release" "$commit" <<'PY'
import json,pathlib,sys
assert json.loads(pathlib.Path(sys.argv[1], 'frontend/dist/runr-release.json').read_text())['commit'] == sys.argv[2]
PY
else
[[ ! -e "$release" ]] || { echo 'Release directory already exists' >&2; exit 1; }
mkdir -p "$release" "$evidence"
tar -xzf "$archive" -C "$release"
ln -s /opt/runr/.venv "$release/.venv"
chmod +x "$release/deploy/start.sh"
publishable_key=$($python_bin - "$current_dist" <<'PY'
import pathlib,re,sys
for path in pathlib.Path(sys.argv[1], 'assets').glob('*.js'):
    match = re.search(r'pk_(?:live|test)_[A-Za-z0-9_=\-]+', path.read_text())
    if match:
        print(match.group()); break
else:
    raise SystemExit('Cannot preserve the production Clerk publishable key')
PY
)
chown -R runr:runr "$release"
install -d -o runr -g runr /var/lib/runr/npm-cache
sudo -u runr npm --prefix "$release/frontend" ci --cache /var/lib/runr/npm-cache > "$evidence/npm-ci.log" 2>&1
(cd "$release/frontend" && sudo -u runr env VITE_CLERK_PUBLISHABLE_KEY="$publishable_key" \
    VITE_API_BASE_URL=https://app.userunr.com/v1 VITE_PERSONALIZED_JOBS_EXPERIENCE=1 \
    VITE_PERSONALIZED_JOBS_DATA_MODE=real VITE_REPLACE_LEGACY_JOBS_NAV=1 VITE_E2E_AUTH=0 VITE_E2E_ADMIN=0 \
    RUNR_RELEASE_COMMIT="$commit" RUNR_RELEASE_BRANCH=release/external-jobs-2026-10-11 \
    npm run build) > "$evidence/frontend-build.log" 2>&1
fi
# Reuse a recent verified backup; make a fresh one if the last is unsuitable.
verify_backup() {
    "$python_bin" - "$evidence/backup-used.json" <<'PY'
import json,pathlib,sys,time
receipt=json.loads(pathlib.Path('/var/lib/runr/customer-backups/latest.json').read_text())
assert 0 <= time.time()-receipt['completed_at'] < 24*60*60, 'A recent backup is required'
assert receipt['integrity_check']=='ok' and receipt['foreign_key_violations']==0
assert receipt['gzip_restore_hash_verified'] and receipt['full_offhost_readback_verified']
pathlib.Path(sys.argv[1]).write_text(json.dumps(receipt,indent=2))
PY
}
if ! verify_backup; then
    systemctl start runr-customer-backup.service
    [[ "$(systemctl show runr-customer-backup.service -p Result --value)" == success ]]
    verify_backup
fi
systemd-run --wait --pipe --collect --unit="runr-external-migrate-$short" \
    -p User=runr -p Group=runr -p SupplementaryGroups=runr-database -p WorkingDirectory="$release" \
    -p EnvironmentFile=/etc/runr/customer-candidate-20261010/api.env \
    -p UnsetEnvironment=RUNR_MIGRATION_HEAD \
    -E LD_LIBRARY_PATH=/usr/local/lib/runr/sqlite-3.54.0 \
    "$python_bin" -m backend.database.migrate --database /var/lib/runr/customer-candidate-db/backend.sqlite3 \
    > "$evidence/migrations.log" 2>&1
cp /etc/nginx/sites-available/runr-public "$evidence/nginx-before.conf"
for role in api worker; do
    systemctl cat "runr-$role-candidate.service" > "$evidence/$role-before.service"
done
switched=false
rollback() {
    if [[ "$switched" == true ]]; then
        cp "$evidence/nginx-before.conf" /etc/nginx/sites-available/runr-public
        rm -f /etc/systemd/system/runr-api-candidate.service.d/external-jobs-release.conf
        rm -f /etc/systemd/system/runr-worker-candidate.service.d/external-jobs-release.conf
        systemctl daemon-reload
        systemctl restart runr-api-candidate.service runr-worker-candidate.service
        nginx -t && systemctl reload nginx
    fi
}
trap rollback ERR
printf 'RUNR_RELEASE_BRANCH=release/external-jobs-2026-10-11\nRUNR_RELEASE_COMMIT=%s\n' "$commit" > /etc/runr/external-jobs-release.env
chmod 600 /etc/runr/external-jobs-release.env
switched=true
for role in api worker; do
    dropin="/etc/systemd/system/runr-$role-candidate.service.d/external-jobs-release.conf"
    mkdir -p "$(dirname "$dropin")"
    {
        printf '[Service]\nWorkingDirectory=%s\nExecStart=\n' "$release"
        if [[ "$role" == api ]]; then
            printf 'ExecStart=%s/deploy/start.sh api\n' "$release"
            printf 'EnvironmentFile=/etc/runr/network-discovery-openrouter.env\n'
        else
            printf 'ExecStart=%s/deploy/start.sh worker --no-auto-retry\n' "$release"
        fi
        printf 'UnsetEnvironment=RUNR_MIGRATION_HEAD\nEnvironmentFile=/etc/runr/external-jobs-release.env\n'
    } > "$dropin"
done
systemctl daemon-reload
systemctl restart runr-api-candidate.service runr-worker-candidate.service
ready=false
for attempt in {1..30}; do
    if curl --fail --silent http://127.0.0.1:18000/health/ready > "$evidence/api-ready.json"; then ready=true; break; fi
    sleep 2
done
[[ "$ready" == true ]]
"$python_bin" - "$current_dist" "$release/frontend/dist" <<'PY'
import pathlib,sys
path=pathlib.Path('/etc/nginx/sites-available/runr-public')
text=path.read_text()
old='root '+sys.argv[1]+';'
assert text.count(old)==1, 'Unexpected production nginx root'
path.write_text(text.replace(old, 'root '+sys.argv[2]+';'))
PY
nginx -t
systemctl reload nginx
curl --fail --silent https://app.userunr.com/health/ready > "$evidence/public-ready.json"
curl --fail --silent https://app.userunr.com/runr-release.json > "$evidence/frontend-release.json"
systemctl is-active runr-api-candidate.service runr-worker-candidate.service
trap - ERR
echo "Installed $commit; evidence: $evidence"
