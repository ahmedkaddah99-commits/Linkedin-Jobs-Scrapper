#!/usr/bin/env bash
# Install an immutable Settings frontend release; retain nginx rollback.
set -euo pipefail
commit="${1:?full release commit required}"
archive="${2:?git archive required}"
resume="${3:-}"
[[ "$commit" =~ ^[0-9a-f]{40}$ && "$EUID" == 0 ]] || exit 1
release="/srv/runr/releases/settings-${commit:0:8}"
evidence="/srv/runr/ops/settings-${commit:0:8}"
python_bin=/opt/runr/.venv/bin/python
[[ "$("$python_bin" --version)" == 'Python 3.12.7' ]] || exit 1
current_dist=$(awk '/^[[:space:]]*root / {gsub(/;/,"",$2); print $2; exit}' /etc/nginx/sites-available/runr-public)
mkdir -p "$release" "$evidence"
if [[ "$resume" == --resume ]]; then
"$python_bin" - "$release/frontend/dist/runr-release.json" "$commit" <<'PY'
import json,pathlib,sys
assert json.loads(pathlib.Path(sys.argv[1]).read_text())['commit']==sys.argv[2]
PY
else
[[ ! -e "$release/frontend" ]] || { echo 'Release already exists' >&2; exit 1; }
tar -xzf "$archive" -C "$release"
publishable_key=$("$python_bin" - "$current_dist" <<'PY'
import pathlib,re,sys
for path in pathlib.Path(sys.argv[1], 'assets').glob('*.js'):
    match=re.search(r'pk_(?:live|test)_[A-Za-z0-9_=\-]+',path.read_text())
    if match:
        print(match.group()); break
else:
    raise SystemExit('Production Clerk publishable key not found')
PY
)
chown -R runr:runr "$release"
sudo -u runr npm --prefix "$release/frontend" ci --cache /var/lib/runr/npm-cache > "$evidence/npm-ci.log" 2>&1
(cd "$release/frontend" && sudo -u runr env VITE_CLERK_PUBLISHABLE_KEY="$publishable_key" \
    VITE_API_BASE_URL=https://app.userunr.com/v1 VITE_PERSONALIZED_JOBS_EXPERIENCE=1 \
    VITE_PERSONALIZED_JOBS_DATA_MODE=real VITE_REPLACE_LEGACY_JOBS_NAV=1 VITE_E2E_AUTH=0 VITE_E2E_ADMIN=0 \
    RUNR_RELEASE_COMMIT="$commit" RUNR_RELEASE_BRANCH=release/settings-2026-10-12 \
    npm run build) > "$evidence/frontend-build.log" 2>&1
fi
cp /etc/nginx/sites-available/runr-public "$evidence/nginx-before.conf"
rollback() {
    cp "$evidence/nginx-before.conf" /etc/nginx/sites-available/runr-public
    nginx -t && systemctl reload nginx
}
trap rollback ERR
"$python_bin" - "$current_dist" "$release/frontend/dist" <<'PY'
import pathlib,sys
path=pathlib.Path('/etc/nginx/sites-available/runr-public')
text=path.read_text(); old='root '+sys.argv[1]+';'
assert text.count(old)==1, 'Unexpected production nginx root'
path.write_text(text.replace(old,'root '+sys.argv[2]+';'))
PY
nginx -t
systemctl reload nginx
verified=false
for attempt in {1..20}; do
curl --fail --silent https://app.userunr.com/runr-release.json > "$evidence/frontend-release.json"
if "$python_bin" - "$evidence/frontend-release.json" "$commit" <<'PY'
import json,pathlib,sys
raise SystemExit(0 if json.loads(pathlib.Path(sys.argv[1]).read_text())['commit']==sys.argv[2] else 1)
PY
then verified=true; break; fi
sleep 1
done
[[ "$verified" == true ]]
"$python_bin" - "$evidence/frontend-release.json" "$commit" <<'PY'
import json,pathlib,sys
assert json.loads(pathlib.Path(sys.argv[1]).read_text())['commit']==sys.argv[2]
PY
curl --fail --silent https://app.userunr.com/health/ready > "$evidence/api-ready.json"
trap - ERR
echo "Installed $commit; evidence: $evidence"
