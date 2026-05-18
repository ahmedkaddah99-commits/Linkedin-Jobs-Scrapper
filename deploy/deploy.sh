#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Missing $PROJECT_DIR/.env"
  exit 1
fi

git pull

set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements-linux.txt"
npm --prefix frontend run build
sudo systemctl daemon-reload
sudo systemctl restart runr.target
sudo systemctl status runr.target --no-pager
