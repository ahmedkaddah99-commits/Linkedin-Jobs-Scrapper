#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Missing $PROJECT_DIR/.env"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

release_commit="${RUNR_RELEASE_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"
release_branch="${RUNR_RELEASE_BRANCH:-$(git branch --show-current 2>/dev/null || true)}"
echo "Deploying selected Runr release commit=${release_commit:-unknown} branch=${release_branch:-unknown}"

"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements-linux.txt"
sudo systemctl daemon-reload
sudo systemctl restart runr.target
sudo systemctl status runr.target --no-pager

cat <<'EOF'
Runtime services were restarted without rebuilding the static frontend.
For a separate frontend release, run:
  npm --prefix frontend ci
  npm --prefix frontend run build
  sudo systemctl restart runr-frontend.service
EOF
