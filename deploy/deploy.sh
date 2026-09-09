#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_PYTHON_VERSION="Python 3.12.7"

cd "$PROJECT_DIR"

if [ ! -f "$PROJECT_DIR/.env" ] || [ ! -f "$PROJECT_DIR/.env.acquisition" ]; then
  echo "Missing $PROJECT_DIR/.env or $PROJECT_DIR/.env.acquisition"
  exit 1
fi

python_bin="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$python_bin" ]; then
  echo "Missing required project interpreter: $python_bin"
  exit 1
fi
actual_python_version="$($python_bin --version 2>&1)"
if [ "$actual_python_version" != "$EXPECTED_PYTHON_VERSION" ]; then
  echo "Expected $EXPECTED_PYTHON_VERSION, got $actual_python_version from $python_bin"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

release_commit="${RUNR_RELEASE_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"
release_branch="${RUNR_RELEASE_BRANCH:-$(git branch --show-current 2>/dev/null || true)}"
echo "Deploying selected Runr release commit=${release_commit:-unknown} branch=${release_branch:-unknown}"

sudo "$python_bin" -m pip install -r "$PROJECT_DIR/requirements-linux.txt"
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
